"""
export_scenarios.py — Pre-bakes historical .npz scenarios and static graph data
into compact JSON files in frontend/public/data/ for zero-backend static web hosting.
"""

import pathlib
import json
import numpy as np

BASE_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SCENARIOS_DIR = DATA_DIR / "scenarios"
OUT_DIR = BASE_DIR.parent / "frontend" / "public" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def export_static_nodes():
    print("Exporting static graph metadata...")
    graph_path = DATA_DIR / "static_graph.npz"
    graph = np.load(graph_path)
    degrees = np.bincount(graph["edge_index"][0], minlength=8001) + np.bincount(graph["edge_index"][1], minlength=8001)

    static_nodes = {
        "elev_m": np.round(graph["elevations"], 2).tolist(),
        "bldg_pct": np.round(graph["building_fracs"] * 100.0, 1).tolist(),
        "area_m2": np.round(graph["effective_areas"], 1).tolist(),
        "connected_pipes": degrees.tolist(),
    }
    out_file = OUT_DIR / "static_nodes.json"
    with open(out_file, "w") as f:
        json.dump(static_nodes, f)
    print(f"Saved {out_file} ({out_file.stat().st_size / 1024:.1f} KB)")

def export_scenario(scenario_id: str, name: str, desc: str):
    path = SCENARIOS_DIR / f"{scenario_id}.npz"
    if not path.exists():
        print(f"Skipping {scenario_id}, file not found.")
        return

    print(f"Processing {scenario_id}...")
    data = np.load(path)
    T = int(data["depth_m"].shape[0])

    # 19 slider steps (0 to 18)
    slider_steps = [min(int(round(s * (T - 1) / 18.0)), T - 1) for s in range(19)]
    steps = []

    for s_idx, t in enumerate(slider_steps):
        depth_cm = np.round(data["depth_m"][t] * 100.0, 1).tolist()
        stored_m3 = np.round(data["stored_vol_m3"][t], 2).tolist()
        rain_rate = round(float(data["rainfall_mm_hr"][t]), 1)
        cum_rain = round(float(np.sum(data["rainfall_mm_hr"][:t + 1]) * (30.0 / 3600.0)), 1)
        steps.append({
            "step": s_idx,
            "sim_t": t,
            "rain_rate": rain_rate,
            "cum_rain": cum_rain,
            "depth_cm": depth_cm,
            "stored_m3": stored_m3,
        })

    payload = {
        "id": scenario_id,
        "name": name,
        "category": "Historical Storm",
        "description": desc,
        "timesteps": T,
        "duration_hours": round(T * 30.0 / 3600.0, 1),
        "peak_intensity_mm_hr": round(float(np.max(data["rainfall_mm_hr"])), 1),
        "steps": steps,
    }

    out_file = OUT_DIR / f"{scenario_id}.json"
    with open(out_file, "w") as f:
        json.dump(payload, f)
    print(f"Saved {out_file} ({out_file.stat().st_size / 1024:.1f} KB)")

if __name__ == "__main__":
    export_static_nodes()
    export_scenario(
        "historical_sept_2025",
        "Kolkata Cloudburst (Sept 2025)",
        "High-intensity 98mm/hr cloudburst inundating Jadavpur & Southern Kolkata."
    )
    export_scenario(
        "historical_2021",
        "Cyclone Yaas Inundation (May 2021)",
        "Severe cyclonic depression causing prolonged tidal-monsoon urban flooding."
    )
    print("Export complete!")
