"""
backend/simulator/run_batch.py — Batch Simulation Runner for GNN Dataset Generation.

1. Generates 200 Latin Hypercube Chicago hyetographs + 2 Historical Replay hyetographs.
2. Extracts and saves the static graph topology ONCE into backend/data/static_graph.npz.
3. Runs VectorizedSimulationEngine across all scenarios at dt=10s, sampling every sample_dt_sec (default 30s).
4. Saves each scenario trajectory as an independent .npz file in backend/data/scenarios/.
"""

import os
import sys
import time
import argparse
from typing import List
import numpy as np

from graph_builder import build_drainage_graph
from surface_grid import build_surface_grid
from kinematic_sim import VectorizedSimulationEngine
from manning_capacity import compute_pipe_capacity
from generate_scenarios import generate_lhs_scenarios, generate_transition_lhs_scenarios, build_historical_scenarios, resample_to_simulator_dt, ScenarioParams


def save_static_graph(drainage: dict, grid: dict, output_path: str = "../data/static_graph.npz"):
    """
    Saves the invariant graph topology and static physical properties once.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    pipe_edges = drainage["pipe_edges"] # [14344, 2]
    from_nodes = pipe_edges[:, 0]
    to_nodes = pipe_edges[:, 1]
    diams = drainage["pipe_diameters"]
    slopes = drainage["pipe_slopes"]
    lengths = drainage["pipe_lengths_m"]
    caps = compute_pipe_capacity(diams, slopes)

    host_cells = grid["manhole_host_cell"] # [8001]
    elevations = drainage["elevations"]    # [8001]
    bldg_fracs = grid["building_fraction"][host_cells]
    effective_areas = grid["cell_effective_area_m2"][host_cells]

    # Edge index COO format: [2, E]
    edge_index = np.vstack([from_nodes, to_nodes])

    np.savez_compressed(
        output_path,
        edge_index=edge_index,
        edge_weight=caps.astype(np.float32), # effective pipe capacity
        pipe_diameters=diams.astype(np.float32),
        pipe_slopes=slopes.astype(np.float32),
        pipe_lengths_m=lengths.astype(np.float32),
        elevations=elevations.astype(np.float32),
        building_fracs=bldg_fracs.astype(np.float32),
        effective_areas=effective_areas.astype(np.float32),
        host_cells=host_cells.astype(np.int32),
        num_nodes=len(elevations),
        num_edges=len(from_nodes)
    )
    print(f"✅ Saved static graph ({len(elevations):,} nodes, {len(from_nodes):,} edges) -> {output_path}")


def run_scenario(
    engine: VectorizedSimulationEngine,
    scenario: ScenarioParams,
    host_cells: np.ndarray,
    sim_dt_sec: float = 10.0,
    sample_dt_sec: float = 30.0,
) -> dict:
    """
    Executes a single scenario through the hydrodynamic simulation engine and samples node time-series.
    """
    # 1. Resample continuous hyetograph to discrete simulation timesteps
    sim_times_sec, sim_rain_mm_hr = resample_to_simulator_dt(
        scenario.times_min,
        scenario.intensity_mm_hr,
        dt_sec=sim_dt_sec
    )

    n_sim_steps = len(sim_times_sec)
    sample_every_n = max(1, int(round(sample_dt_sec / sim_dt_sec)))

    # Reset engine state (clear water depths & stored volumes)
    engine.surface_depths.fill(0.0)

    sampled_times_sec = []
    sampled_rain_mm_hr = []
    sampled_depths_m = []
    sampled_stored_vol_m3 = []

    for step in range(n_sim_steps):
        rain = float(sim_rain_mm_hr[step])
        res = engine.step(rainfall_mm_per_hr=rain, timestep_seconds=sim_dt_sec)

        if step % sample_every_n == 0:
            # Map 2D surface grid depths onto the 8,001 host manhole junctions
            surf_depths = res["surface_depths_m"]
            m_depths = surf_depths[host_cells]
            m_overflow = res["manhole_overflow_m3"]

            sampled_times_sec.append(float(sim_times_sec[step]))
            sampled_rain_mm_hr.append(rain)
            sampled_depths_m.append(m_depths.astype(np.float32))
            sampled_stored_vol_m3.append(m_overflow.astype(np.float32))

    return {
        "scenario_id": scenario.scenario_id,
        "source": scenario.source,
        "peak_intensity_mm_hr": scenario.peak_intensity_mm_hr,
        "duration_min": scenario.duration_min,
        "total_depth_mm": scenario.total_depth_mm,
        "times_sec": np.array(sampled_times_sec, dtype=np.float32),
        "rainfall_mm_hr": np.array(sampled_rain_mm_hr, dtype=np.float32),
        "depth_m": np.array(sampled_depths_m, dtype=np.float32), # [T, 8001]
        "stored_vol_m3": np.array(sampled_stored_vol_m3, dtype=np.float32), # [T, 8001]
    }


def run_batch_pipeline(
    n_lhs: int = 200,
    n_trans: int = 60,
    out_dir: str = "../data/scenarios",
    static_graph_path: str = "../data/static_graph.npz",
    sim_dt_sec: float = 10.0,
    sample_dt_sec: float = 30.0,
):
    """
    Main batch generation pipeline for full 262-scenario dataset.
    """
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 70)
    print("  HYDRODYNAMIC BATCH SIMULATION RUNNER (262 SCENARIOS)")
    print("=" * 70)

    # 1. Build Geospatial Infrastructure
    print("\n── 1. Initializing Drainage Graph & 2D Surface Mesh ──")
    drainage = build_drainage_graph(verbose=False)
    grid = build_surface_grid(drainage, verbose=False)
    engine = VectorizedSimulationEngine(surface_grid=grid, drainage_graph=drainage)
    host_cells = grid["manhole_host_cell"]

    # 2. Save Static Graph Structure
    save_static_graph(drainage, grid, static_graph_path)

    # 3. Generate Scenario Hyetographs
    print(f"\n── 2. Generating Scenario Hyetographs ({n_lhs} LHS + {n_trans} Transition + 2 Historical) ──")
    lhs_scenarios = generate_lhs_scenarios(n_scenarios=n_lhs, seed=42)
    trans_scenarios = generate_transition_lhs_scenarios(n_scenarios=n_trans, seed=9999)
    hist_scenarios = build_historical_scenarios()
    all_scenarios = lhs_scenarios + trans_scenarios + hist_scenarios

    print(f"Total scenarios to simulate: {len(all_scenarios)}")

    # 4. Execute Batch Simulations
    print("\n── 3. Executing Coupled 2D/1D Simulations ──")
    total_start = time.time()
    total_timesteps_collected = 0

    for idx, sc in enumerate(all_scenarios, 1):
        t0 = time.time()
        result = run_scenario(
            engine=engine,
            scenario=sc,
            host_cells=host_cells,
            sim_dt_sec=sim_dt_sec,
            sample_dt_sec=sample_dt_sec
        )
        elapsed = time.time() - t0
        n_steps = len(result["times_sec"])
        total_timesteps_collected += n_steps

        # Save scenario .npz
        out_file = os.path.join(out_dir, f"{sc.scenario_id}.npz")
        np.savez_compressed(out_file, **result)

        peak_inundation_cm = float(np.max(result["depth_m"])) * 100.0
        print(f"  [{idx:03d}/{len(all_scenarios):03d}] {sc.scenario_id:<22} "
              f"({sc.source}) │ Peak: {sc.peak_intensity_mm_hr:5.1f} mm/h │ "
              f"Max Depth: {peak_inundation_cm:5.1f} cm │ {n_steps:3d} steps │ {elapsed:.2f}s")

    total_time = time.time() - total_start
    print("\n" + "=" * 70)
    print(f"✅ BATCH SIMULATION COMPLETED in {total_time:.1f}s!")
    print(f"   Generated: {len(all_scenarios)} scenario files in {out_dir}")
    print(f"   Total Timestep Observations: {total_timesteps_collected:,} graph states")
    print(f"   Total Node-Timestep Pairs:   {total_timesteps_collected * 8001:,}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run batch simulations for GNN dataset")
    parser.add_argument("--n_lhs", type=int, default=50, help="Number of Latin Hypercube scenarios to generate (default: 50)")
    parser.add_argument("--out_dir", type=str, default="../data/scenarios", help="Output directory for .npz files")
    args = parser.parse_args()

    run_batch_pipeline(n_lhs=args.n_lhs, out_dir=args.out_dir)
