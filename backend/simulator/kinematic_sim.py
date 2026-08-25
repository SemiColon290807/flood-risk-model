
import numpy as np
from manning_capacity import compute_pipe_capacity, apply_blockage
from surface_routing import rainfall_to_depth_increase, compute_lateral_transfer_batch


#Using numpy vectorisation increases computation speed by 50x-200x
class VectorizedSimulationEngine:

    def __init__(self, elevations, areas, pipe_edges, pipe_diameters, pipe_slopes, pipe_roughnesses= None, pipe_blockages=None):

        self.num_cells = len(elevations)
        self.num_pipes= len(pipe_edges)

        self.elevations= np.array(elevations, dtype=np.float64)
        self.areas= np.array(areas, dtype=np.float64)
        self.depths= np.zeros(self.num_cells, dtype=np.float64)
        
        self.pipe_edges= np.array(pipe_edges, dtype=np.int32)
        self.pipe_diameters= np.array(pipe_diameters, dtype=np.float64)
        self.pipe_slopes= np.array(pipe_slopes, dtype=np.float64)

        if pipe_roughnesses is not None:
            self.pipe_roughnesses = np.array(pipe_roughnesses, dtype=np.float64)
        else:
            self.pipe_roughnesses = np.full(self.num_pipes, 0.017, dtype=np.float64)

        if pipe_blockages is not None:
            self.pipe_blockages = np.array(pipe_blockages, dtype=np.float64)
        else:
            self.pipe_blockages = np.zeros(self.num_pipes, dtype=np.float64)

        self._compute_effective_capacities()
    
    def _compute_effective_capacities(self):
        base_capacities = compute_pipe_capacity(self.pipe_diameters, self.pipe_slopes, self.pipe_roughnesses)
        self.effective_capacities = apply_blockage(base_capacities, self.pipe_blockages)
    
    #This function allows us to update blockages from the client side. 
    def update_pipe_blockage(self, pipe_idx, blockage_pct):
        self.pipe_blockages[pipe_idx] = blockage_pct
        self._compute_effective_capacities()

    def step(self, rainfall_mm_per_hr, timestep_seconds, runoff_coefficient=0.85, neighbor_idx_i=None, neighbor_idx_j=None, neighbor_dist_m=10.0, neighbor_width_m=10.0):
        dt = timestep_seconds
        from_nodes = self.pipe_edges[:, 0]
        to_nodes   = self.pipe_edges[:, 1]

    #Adding rainfall:

        depth_inc = rainfall_to_depth_increase(rainfall_mm_per_hr, dt, runoff_coefficient)
        self.depths += depth_inc

    #Surface inlet drainage:
        max_outlet_cap = np.bincount(from_nodes, weights=self.effective_capacities, minlength=self.num_cells)
        standing_vols  = self.depths * self.areas
        max_drain_vols = max_outlet_cap * dt
        drained_vols   = np.minimum(standing_vols, max_drain_vols)
        self.depths   -= drained_vols / self.areas

    #Subsurface Routing and backflow
        subsurface_inflow = drained_vols.copy()
        overflow_vols     = np.zeros(self.num_cells, dtype=np.float64)
        sorted_cell_idx   = np.argsort(-self.elevations)

        for u in sorted_cell_idx:
            inflow = subsurface_inflow[u]
            if inflow <= 0.0:
                continue
            pipe_mask = (from_nodes == u)
            if not np.any(pipe_mask):
                continue  # Outfall/terminal node — freely drains
            out_caps      = self.effective_capacities[pipe_mask]
            total_out_cap = np.sum(out_caps)
            max_out_vol   = total_out_cap * dt
            if inflow <= max_out_vol:
                transferred = inflow
            else:
                transferred = max_out_vol
                overflow    = inflow - max_out_vol
                overflow_vols[u] += overflow
                self.depths[u]   += overflow / self.areas[u]

            # Distribute transferred volume downstream proportional to pipe capacity
            if total_out_cap > 0:
                downstream = to_nodes[pipe_mask]
                fractions  = out_caps / total_out_cap
                np.add.at(subsurface_inflow, downstream, transferred * fractions)

    #Phase 4 — 2D Surface sheet-flow lateral redistribution:
        if neighbor_idx_i is not None and len(neighbor_idx_i) > 0:
            idx_i = np.asarray(neighbor_idx_i, dtype=np.int32)
            idx_j = np.asarray(neighbor_idx_j, dtype=np.int32)

            sheet_dt = min(dt, 5.0)  # Stability cap for flat JU campus terrain

            signed_vols = compute_lateral_transfer_batch(
                elevations=self.elevations,
                depths=self.depths,
                areas=self.areas,
                idx_i=idx_i,
                idx_j=idx_j,
                dist_m=neighbor_dist_m,
                width_m=neighbor_width_m,
                timestep_seconds=sheet_dt
            )

            area_i = self.areas[idx_i]
            area_j = self.areas[idx_j]
            np.add.at(self.depths, idx_i, -signed_vols / area_i)
            np.add.at(self.depths, idx_j,  signed_vols / area_j)

        # Clamp depths to zero to prevent floating-point drift negatives
        np.maximum(self.depths, 0.0, out=self.depths)

        return {
            "depths_m":         self.depths.copy(),
            "wse_m":            self.elevations + self.depths,
            "overflow_vols_m3": overflow_vols
        }
