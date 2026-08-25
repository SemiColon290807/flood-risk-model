import numpy as np

def manning_flow(area_m2, hydraulic_radius_m, slope, roughness):
   #returns flow rate in m^3/s
    if slope <= 0:
        # A pipe or surface with zero/negative slope isn't cleanly handled
        # by Manning's equation (S^0.5 of a negative number is undefined,
        # and zero slope would give zero capacity, which incorrectly
        # implies water can NEVER move through flat sections). 
        # Hence using a small positive value.
        slope = 1e-4
    return (1.0 / roughness) * area_m2 * (hydraulic_radius_m ** (2.0 / 3.0)) * (slope**0.5)

def compute_pipe_capacity(diameters, slopes, roughnesses=0.017, min_slope=1e-4):
    diameters = np.asarray(diameters, dtype=np.float64)
    slopes = np.asarray(slopes, dtype=np.float64)
    roughnesses = np.asarray(roughnesses, dtype=np.float64)

    area = np.pi * (diameters ** 2) / 4.0
    hydraulic_radius = diameters / 4.0  # valid for a circular pipe flowing full
    slopes_safe = np.maximum(slopes, min_slope)

    capacity = (1.0 / roughnesses) * area * (hydraulic_radius ** (2.0 / 3.0)) * np.sqrt(slopes_safe)
    return capacity

#Keeping in mind the condition of maintainence of the Indian Drainage system in general, We make a conservative estimate of the Manning's coefficient for a concrete pipe.

def apply_blockage(capacities, blockage_pct):
   
    capacities = np.asarray(capacities, dtype=np.float64)
    blockage_pct = np.asarray(blockage_pct, dtype=np.float64)

    blockage_factor = 1.0 - np.clip(blockage_pct, 0.0, 1.0)
    return capacities * blockage_factor

#Assuming that a blockage fraction affects the effective capacity linearly
#(Simplification since the blockage fraction affects the hydraulic radius as well
#Resulting change is not linear.


#Added numpy vectorization to be used in kinetic_sim.py
