import numpy as np

def rainfall_to_depth_increase(rainfall_mm_per_hr, timestep_seconds, runoff_coefficient=0.85):
    rainfall_mm_per_hr = np.asarray(rainfall_mm_per_hr, dtype=np.float64)
    runoff_coefficient = np.asarray(runoff_coefficient, dtype=np.float64)

    rainfall_m_per_s = (rainfall_mm_per_hr / 1000.0) / 3600.0  # mm/hr -> m/s
    depth_increase = rainfall_m_per_s * timestep_seconds * runoff_coefficient
    return depth_increase

def compute_sheet_flow_per_width(depth_m, slope, roughness=0.035, min_slope=1e-4):
   
    depth_m = np.asarray(depth_m, dtype=np.float64)
    slope = np.asarray(slope, dtype=np.float64)

    safe_depth = np.maximum(depth_m, 0.0)
    safe_slope = np.maximum(slope, min_slope)

    return (1.0 / roughness) * (safe_depth ** (5.0 / 3.0)) * (safe_slope ** 0.5)

    #Here Area= depth, and hydraulic radius is also equal to depth. Check Derivation

def compute_water_surface_elevation(ground_elevation_m, water_depth_m):

    return ground_elevation_m + water_depth_m

#Lateral transfer is the amount of water that flows from cell i to j
#cell_i is a dict describing the cell's current state. 
# eg: {"elevation_m"(actual ground elevation): 10.0, "depth_m": 0.05, "area_m2": 2500}

def compute_lateral_transfer_batch(elevations, depths, areas, idx_i, idx_j, dist_m, width_m, timestep_seconds, roughness=0.035):
    
    wse = elevations + depths
    wse_i = wse[idx_i]
    wse_j = wse[idx_j]

    delta_wse = wse_i - wse_j
    signed_vols = np.zeros(len(idx_i), dtype=np.float64)

    mask_flow = np.abs(delta_wse) > 1e-6
    if not np.any(mask_flow):
        return signed_vols

    i_f = idx_i[mask_flow]
    j_f = idx_j[mask_flow]
    delta_f = delta_wse[mask_flow]
    abs_delta_f = np.abs(delta_f)

    dist_f = dist_m if np.isscalar(dist_m) else np.asarray(dist_m)[mask_flow]
    width_f = width_m if np.isscalar(width_m) else np.asarray(width_m)[mask_flow]

    upstream_depths = np.where(delta_f > 0, depths[i_f], depths[j_f])
    slope_f = abs_delta_f / dist_f

    q_per_width = compute_sheet_flow_per_width(upstream_depths, slope_f, roughness)
    raw_vols = q_per_width * width_f * timestep_seconds

    area_i = areas[i_f]
    area_j = areas[j_f]
    equalize_vols = abs_delta_f / ((1.0 / area_i) + (1.0 / area_j))

    capped_vols = np.minimum(raw_vols, equalize_vols)
    signed_vols[mask_flow] = np.where(delta_f > 0, capped_vols, -capped_vols)

    return signed_vols



