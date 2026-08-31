"""
kinematic_sim.py — Coupled 2D Surface Porosity & 1D Subsurface Drainage Simulator.

Orchestrates the 4-phase coupled hydrodynamic simulation loop:
    Phase 1: Dual-porosity surface rainfall addition (concentrating on open ground).
    Phase 2: Distance-capped inlet drainage (cells <= 50m to manholes).
    Phase 3: Underground cascading pipe hydraulics & host-cell surcharge backflow.
    Phase 4: Sub-stepped 2D overland sheet flow with conveyance porosity.
"""

import numpy as np
from manning_capacity import compute_pipe_capacity, apply_blockage
from surface_routing import compute_lateral_transfer_batch


class VectorizedSimulationEngine:
    def __init__(self, surface_grid, drainage_graph, pipe_roughnesses=None, pipe_blockages=None):
        # ── 1. Surface Grid Layer (10,000 cells) ──
        self.num_cells = len(surface_grid["cell_elevations"])
        self.cell_elevations = np.array(surface_grid["cell_elevations"], dtype=np.float64)
        self.cell_areas_m2 = np.array(surface_grid["cell_areas_m2"], dtype=np.float64)
        self.cell_effective_areas_m2 = np.array(surface_grid["cell_effective_area_m2"], dtype=np.float64)
        self.c_cell = np.array(surface_grid["c_cell"], dtype=np.float64)
        self.surface_depths = np.zeros(self.num_cells, dtype=np.float64)

        # 2D surface neighbor connectivity
        pairs = np.array(surface_grid["neighbor_pairs"], dtype=np.int32)
        self.pair_i = pairs[:, 0]
        self.pair_j = pairs[:, 1]
        self.neighbor_dist_m = float(surface_grid.get("neighbor_dist_m", 40.0))
        self.neighbor_effective_widths_m = np.array(surface_grid["neighbor_effective_width_m"], dtype=np.float64)

        # Spatial coupling: 50m inlet mask & manhole host cells
        self.manhole_assignment = np.array(surface_grid["manhole_assignment"], dtype=np.int32)
        self.has_inlet = np.array(surface_grid["has_inlet"], dtype=bool)
        self.manhole_host_cell = np.array(surface_grid["manhole_host_cell"], dtype=np.int32)

        # ── 2. Drainage Network Layer (8,001 manholes, 14,344 pipes) ──
        self.num_manholes = len(drainage_graph["elevations"])
        self.num_pipes = len(drainage_graph["pipe_diameters"])
        self.manhole_elevations = np.array(drainage_graph["elevations"], dtype=np.float64)
        self.pipe_edges = np.array(drainage_graph["pipe_edges"], dtype=np.int32)
        self.from_nodes = self.pipe_edges[:, 0]
        self.to_nodes = self.pipe_edges[:, 1]
        self.pipe_diameters = np.array(drainage_graph["pipe_diameters"], dtype=np.float64)
        self.pipe_slopes = np.array(drainage_graph["pipe_slopes"], dtype=np.float64)

        if pipe_roughnesses is not None:
            self.pipe_roughnesses = np.array(pipe_roughnesses, dtype=np.float64)
        else:
            self.pipe_roughnesses = np.full(self.num_pipes, 0.017, dtype=np.float64)

        if pipe_blockages is not None:
            self.pipe_blockages = np.array(pipe_blockages, dtype=np.float64)
        else:
            self.pipe_blockages = np.zeros(self.num_pipes, dtype=np.float64)

        # High-to-low topological sweep order
        self.sorted_manholes = np.argsort(-self.manhole_elevations)

        # Pre-computed O(1) adjacency lookup for Phase 3
        self.outgoing_pipes = [[] for _ in range(self.num_manholes)]
        for p_idx, u in enumerate(self.from_nodes):
            self.outgoing_pipes[u].append(p_idx)

        # ── True Terminal Outfall vs. Interior Dead-End Classification ──
        # Heuristic based on network bounding-box position (5% border buffer):
        # Nodes with 0 outgoing pipes at the spatial boundary of the domain represent
        # legitimate outfalls to regional canals/rivers and discharge freely.
        # Zero-outdegree nodes in the interior are dead-end junctions with no downhill
        # pipe connection and must surcharge 100% of incoming water back to their host surface cell.
        if "eastings" in drainage_graph and "northings" in drainage_graph:
            eastings = np.array(drainage_graph["eastings"], dtype=np.float64)
            northings = np.array(drainage_graph["northings"], dtype=np.float64)
            min_e, max_e = np.min(eastings), np.max(eastings)
            min_n, max_n = np.min(northings), np.max(northings)
            e_range = max(max_e - min_e, 1.0)
            n_range = max(max_n - min_n, 1.0)
            rel_e = (eastings - min_e) / e_range
            rel_n = (northings - min_n) / n_range
            is_boundary = (rel_e < 0.05) | (rel_e > 0.95) | (rel_n < 0.05) | (rel_n > 0.95)
        else:
            is_boundary = np.zeros(self.num_manholes, dtype=bool)

        self.is_true_outfall = np.array([
            (len(self.outgoing_pipes[u]) == 0 and is_boundary[u])
            for u in range(self.num_manholes)
        ], dtype=bool)

        self._compute_effective_capacities()

    def _compute_effective_capacities(self):
        base_caps = compute_pipe_capacity(self.pipe_diameters, self.pipe_slopes, self.pipe_roughnesses)
        self.effective_capacities = apply_blockage(base_caps, self.pipe_blockages)
        self.manhole_total_out_cap = np.bincount(self.from_nodes, weights=self.effective_capacities, minlength=self.num_manholes)

    def update_pipe_blockage(self, pipe_idx, blockage_pct):
        self.pipe_blockages[pipe_idx] = blockage_pct
        self._compute_effective_capacities()

    def step(self, rainfall_mm_per_hr, timestep_seconds, sheet_sub_dt=5.0):
        dt = float(timestep_seconds)

        # ── Phase 1: Dual-Porosity Rainfall on Surface Grid ──
        if rainfall_mm_per_hr > 0.0:
            rain_m = (rainfall_mm_per_hr / 1000.0) * (dt / 3600.0)
            rain_vol_m3 = rain_m * self.c_cell * self.cell_areas_m2
            self.surface_depths += rain_vol_m3 / self.cell_effective_areas_m2

        # ── Phase 2: Distance-Capped Surface Inlet Drainage ──
        standing_vols = self.surface_depths * self.cell_effective_areas_m2
        inlet_cell_indices = np.where(self.has_inlet)[0]
        assigned_m = self.manhole_assignment[inlet_cell_indices]

        # Max inlet drainage per cell based on connected manhole's total out capacity
        m_caps = self.manhole_total_out_cap[assigned_m]
        max_drain_vols = m_caps * dt
        drained_vols = np.minimum(standing_vols[inlet_cell_indices], max_drain_vols)

        self.surface_depths[inlet_cell_indices] -= drained_vols / self.cell_effective_areas_m2[inlet_cell_indices]
        subsurface_inflow = np.bincount(assigned_m, weights=drained_vols, minlength=self.num_manholes)

        # ── Phase 3: Downhill Subsurface Routing & Host-Cell Backflow ──
        overflow_vols = np.zeros(self.num_manholes, dtype=np.float64)

        for u in self.sorted_manholes:
            inflow = subsurface_inflow[u]
            if inflow <= 0.0:
                continue

            out_pipes = self.outgoing_pipes[u]
            if len(out_pipes) == 0:
                if self.is_true_outfall[u]:
                    # Legitimate boundary outfall: free terminal discharge out of domain
                    continue
                else:
                    # Interior dead-end junction: 100% of subsurface inflow surcharges onto host surface cell
                    overflow_vols[u] += inflow
                    host_c = self.manhole_host_cell[u]
                    self.surface_depths[host_c] += inflow / self.cell_effective_areas_m2[host_c]
                    continue

            total_out_cap = self.manhole_total_out_cap[u]
            max_out_vol = total_out_cap * dt

            if inflow <= max_out_vol:
                transferred = inflow
            else:
                transferred = max_out_vol
                overflow = inflow - max_out_vol
                overflow_vols[u] += overflow

                # Backflow spills directly onto the manhole's host cell
                host_c = self.manhole_host_cell[u]
                self.surface_depths[host_c] += overflow / self.cell_effective_areas_m2[host_c]

            # Distribute transferred volume downstream
            if total_out_cap > 0:
                for p_idx in out_pipes:
                    to_n = self.to_nodes[p_idx]
                    frac = self.effective_capacities[p_idx] / total_out_cap
                    subsurface_inflow[to_n] += transferred * frac

        # ── Phase 4: Sub-stepped 2D Surface Sheet Flow with Porosity ──
        if len(self.pair_i) > 0:
            n_substeps = max(1, int(np.ceil(dt / sheet_sub_dt)))
            sub_dt = dt / n_substeps

            for _ in range(n_substeps):
                signed_vols = compute_lateral_transfer_batch(
                    elevations=self.cell_elevations,
                    depths=self.surface_depths,
                    areas=self.cell_effective_areas_m2,
                    idx_i=self.pair_i,
                    idx_j=self.pair_j,
                    dist_m=self.neighbor_dist_m,
                    width_m=self.neighbor_effective_widths_m,
                    timestep_seconds=sub_dt,
                )
                np.add.at(self.surface_depths, self.pair_i, -signed_vols / self.cell_effective_areas_m2[self.pair_i])
                np.add.at(self.surface_depths, self.pair_j,  signed_vols / self.cell_effective_areas_m2[self.pair_j])
                np.maximum(self.surface_depths, 0.0, out=self.surface_depths)

        return {
            "surface_depths_m": self.surface_depths.copy(),
            "wse_m": self.cell_elevations + self.surface_depths,
            "manhole_overflow_m3": overflow_vols,
        }


# ── Quick CLI Verification ──
if __name__ == "__main__":
    import time
    from graph_builder import build_drainage_graph
    from surface_grid import build_surface_grid

    print("Building full coupled model...")
    drainage = build_drainage_graph(verbose=False)
    grid = build_surface_grid(drainage, verbose=False)

    print(f"Drainage network: {len(drainage['elevations']):,} manholes, {len(drainage['pipe_diameters']):,} pipes")
    print(f"Surface grid:     {len(grid['cell_elevations']):,} cells, {len(grid['neighbor_pairs']):,} neighbor pairs")

    engine = VectorizedSimulationEngine(surface_grid=grid, drainage_graph=drainage)

    print("\nRunning test storm: 60 mm/hr for 1 hour (360 x 10s timesteps)...")
    rainfall_rate = 60.0  # mm/hr
    dt = 10.0            # seconds
    n_steps = 360

    t0 = time.perf_counter()
    for step in range(n_steps):
        res = engine.step(rainfall_mm_per_hr=rainfall_rate, timestep_seconds=dt)
    t1 = time.perf_counter()

    elapsed = t1 - t0
    per_step_ms = (elapsed / n_steps) * 1000.0

    print(f"\nCompleted in {elapsed:.2f}s (mean {per_step_ms:.1f} ms/step)!")
    print(f"Max surface flood depth: {res['surface_depths_m'].max():.3f} m")
    print(f"Mean surface flood depth: {res['surface_depths_m'].mean():.3f} m")
    print(f"Total surcharged overflow volume: {res['manhole_overflow_m3'].sum():.2f} m^3")
