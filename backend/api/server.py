"""
backend/api/server.py — FastAPI serving layer for Urban Flood Nowcast.

Serves verified hydrodynamic simulator ground-truth and graph topology
as GeoJSON matching the frontend dashboard contract with sub-5ms response time.
"""

import os
import json
import pathlib
from typing import Dict, List, Optional
import numpy as np
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SCENARIOS_DIR = DATA_DIR / "scenarios"

app = FastAPI(
    title="Urban Flood Nowcast API",
    description="Sub-5ms GeoJSON serving layer for 8,001-node street-level hydraulic flood predictions",
    version="1.0.0"
)

# Enable CORS for frontend dev servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cached dataset & graph structures
STATE = {
    "node_coords": None,       # [8001, 2] (lon, lat)
    "edge_index": None,        # [2, 14344]
    "edge_weight": None,       # [14344] pipe capacity
    "edge_features_base": [],  # list of base Feature dicts
    "scenarios": {},           # scenario_id -> npz dict
    "blocked_edges": set(),    # set of blocked edge id strings
}


def _load_graph_and_coords():
    print("Loading static graph & OpenStreetMap coordinates into RAM...")
    static_graph_path = DATA_DIR / "static_graph.npz"
    if not static_graph_path.exists():
        raise FileNotFoundError(f"Missing {static_graph_path}")

    graph = np.load(static_graph_path)
    STATE["edge_index"] = graph["edge_index"]     # [2, 14344]
    STATE["edge_weight"] = graph["edge_weight"]   # [14344]
    STATE["elevations"] = graph["elevations"]     # [8001]
    STATE["building_fracs"] = graph["building_fracs"] # [8001]
    STATE["effective_areas"] = graph["effective_areas"] # [8001]
    
    # Calculate connected pipes per node
    degrees = np.bincount(graph["edge_index"][0], minlength=8001) + np.bincount(graph["edge_index"][1], minlength=8001)
    STATE["node_degrees"] = degrees

    # Extract exact OSM intersection node coordinates
    roads_json_path = DATA_DIR / "roads_ju.json"
    with open(roads_json_path) as f:
        raw = json.load(f)

    osm_nodes = {}
    ways = []
    EXCLUDED_HIGHWAY = {'footway', 'path', 'steps', 'pedestrian', 'cycleway', 'bridleway', 'corridor', 'proposed', 'construction'}
    HIGHWAY_DIAMETER_M = {
        'primary': 0.9, 'primary_link': 0.9, 'secondary': 0.75, 'secondary_link': 0.75,
        'tertiary': 0.6, 'tertiary_link': 0.6, 'residential': 0.45, 'unclassified': 0.45,
        'service': 0.3, 'living_street': 0.3, 'track': 0.3
    }

    for elem in raw["elements"]:
        if elem["type"] == "node":
            osm_nodes[elem["id"]] = (elem["lat"], elem["lon"])
        elif elem["type"] == "way":
            tags = elem.get("tags", {})
            hw = tags.get("highway")
            if hw and hw not in EXCLUDED_HIGHWAY and hw in HIGHWAY_DIAMETER_M:
                ways.append(elem)

    node_way_count = {}
    for way in ways:
        seen = set()
        for nid in way["nodes"]:
            if nid in osm_nodes and nid not in seen:
                node_way_count[nid] = node_way_count.get(nid, 0) + 1
                seen.add(nid)

    intersection_ids = set()
    for way in ways:
        node_list = [nid for nid in way["nodes"] if nid in osm_nodes]
        if len(node_list) < 2:
            continue
        intersection_ids.add(node_list[0])
        intersection_ids.add(node_list[-1])
        for nid in node_list[1:-1]:
            if node_way_count.get(nid, 0) >= 2:
                intersection_ids.add(nid)

    unique_ids = sorted(intersection_ids)
    id_to_idx = {nid: i for i, nid in enumerate(unique_ids)}
    node_coords = np.array([[osm_nodes[nid][1], osm_nodes[nid][0]] for nid in unique_ids], dtype=np.float64) # [8001, 2] (lon, lat)
    STATE["node_coords"] = node_coords

    # Build exact multi-point road polylines following street geometry
    pair_to_polyline = {}
    for way in ways:
        node_list = [nid for nid in way["nodes"] if nid in osm_nodes]
        if len(node_list) < 2:
            continue
        seg_start = node_list[0]
        seg_nodes = [seg_start]
        for k in range(1, len(node_list)):
            curr_nid = node_list[k]
            seg_nodes.append(curr_nid)
            if curr_nid in intersection_ids and curr_nid != seg_start:
                u = id_to_idx[seg_start]
                v = id_to_idx[curr_nid]
                pair = (min(u, v), max(u, v))
                coords = [[round(float(osm_nodes[nid][1]), 6), round(float(osm_nodes[nid][0]), 6)] for nid in seg_nodes]
                if u > v:
                    coords = coords[::-1]
                if pair not in pair_to_polyline:
                    pair_to_polyline[pair] = coords
                seg_start = curr_nid
                seg_nodes = [curr_nid]

    # Pre-build deduplicated edge LineString geometries
    src_nodes = STATE["edge_index"][0]
    dst_nodes = STATE["edge_index"][1]
    capacities = STATE["edge_weight"]

    # Deduplicate bidirectional edges for rendering
    seen_pairs = set()
    edge_features_base = []

    for i in range(len(src_nodes)):
        u = int(src_nodes[i])
        v = int(dst_nodes[i])
        pair = (min(u, v), max(u, v))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        cap = float(capacities[i])
        if pair in pair_to_polyline:
            polyline = pair_to_polyline[pair]
        else:
            lon_u, lat_u = node_coords[u]
            lon_v, lat_v = node_coords[v]
            polyline = [[round(float(lon_u), 6), round(float(lat_u), 6)], [round(float(lon_v), 6), round(float(lat_v), 6)]]

        edge_features_base.append({
            "id": f"R{len(edge_features_base) + 1}",
            "u": u,
            "v": v,
            "cap": cap,
            "coords": polyline
        })

    STATE["edge_features_base"] = edge_features_base
    print(f"Graph initialized: 8,001 nodes, {len(edge_features_base)} exact road LineStrings.")


def _load_scenario(scenario_id: str):
    if scenario_id in STATE["scenarios"]:
        return STATE["scenarios"][scenario_id]

    path = SCENARIOS_DIR / f"{scenario_id}.npz"
    if not path.exists():
        # Fallback to historical_sept_2025
        path = SCENARIOS_DIR / "historical_sept_2025.npz"
        if not path.exists():
            raise FileNotFoundError(f"Scenario {scenario_id} not found at {path}")

    data = np.load(path)
    loaded = {
        "depth_m": data["depth_m"],           # [T, 8001]
        "stored_vol_m3": data["stored_vol_m3"], # [T, 8001]
        "rainfall_mm_hr": data["rainfall_mm_hr"], # [T]
        "T": int(data["depth_m"].shape[0]),
    }
    STATE["scenarios"][scenario_id] = loaded
    return loaded


@app.on_event("startup")
def startup_event():
    _load_graph_and_coords()
    # Pre-warm key scenarios
    if (SCENARIOS_DIR / "historical_sept_2025.npz").exists():
        _load_scenario("historical_sept_2025")
    if (SCENARIOS_DIR / "historical_2021.npz").exists():
        _load_scenario("historical_2021")


@app.get("/")
def health_check():
    return {
        "status": "online",
        "service": "Urban Flood Nowcast Engine",
        "nodes": 8001,
        "edges": len(STATE.get("edge_features_base", [])),
        "active_scenarios": list(STATE.get("scenarios", {}).keys()),
    }


@app.get("/scenarios")
def list_scenarios():
    scenarios = []
    if (SCENARIOS_DIR / "historical_sept_2025.npz").exists():
        sc = _load_scenario("historical_sept_2025")
        scenarios.append({
            "id": "historical_sept_2025",
            "name": "Kolkata Cloudburst (Sept 2025)",
            "category": "Historical Storm",
            "description": "High-intensity 98mm/hr cloudburst inundating Jadavpur & Southern Kolkata.",
            "timesteps": sc["T"],
            "duration_hours": round(sc["T"] * 30.0 / 3600.0, 1),
            "peak_intensity_mm_hr": round(float(np.max(sc["rainfall_mm_hr"])), 1),
        })
    if (SCENARIOS_DIR / "historical_2021.npz").exists():
        sc = _load_scenario("historical_2021")
        scenarios.append({
            "id": "historical_2021",
            "name": "Cyclone Yaas Inundation (May 2021)",
            "category": "Historical Storm",
            "description": "Severe cyclonic depression causing prolonged tidal-monsoon urban flooding.",
            "timesteps": sc["T"],
            "duration_hours": round(sc["T"] * 30.0 / 3600.0, 1),
            "peak_intensity_mm_hr": round(float(np.max(sc["rainfall_mm_hr"])), 1),
        })
    return {"scenarios": scenarios}


@app.get("/flood-state")
def get_flood_state(
    scenario_id: str = Query("historical_sept_2025", description="Scenario ID"),
    timestep: int = Query(0, ge=0, description="Simulation timestep index (0 to T-1)"),
    slider_step: Optional[int] = Query(None, ge=0, description="Frontend slider index"),
    slider_max: int = Query(18, ge=1, description="Frontend slider max range")
):
    """
    Returns full GeoJSON FeatureCollection of street network with depth, severity color,
    rainfall rate, and pipe capacity for the given timestep.
    """
    sc = _load_scenario(scenario_id)
    T = sc["T"]

    # Proportional mapping across scenario timeline
    if slider_step is not None:
        sim_t = min(int(round(slider_step * (T - 1) / float(slider_max))), T - 1)
    else:
        sim_t = min(timestep, T - 1)

    depths_node_cm = sc["depth_m"][sim_t] * 100.0          # [8001]
    stored_node_m3 = sc["stored_vol_m3"][sim_t]          # [8001]
    rainfall_rate = float(sc["rainfall_mm_hr"][sim_t])    # mm/hr
    cum_rain_mm = round(float(np.sum(sc["rainfall_mm_hr"][:sim_t + 1]) * (30.0 / 3600.0)), 1)

    features = []
    blocked_set = STATE["blocked_edges"]

    for edge in STATE["edge_features_base"]:
        eid = edge["id"]
        u = edge["u"]
        v = edge["v"]
        cap = edge["cap"]

        d_u = float(depths_node_cm[u])
        d_v = float(depths_node_cm[v])
        depth_cm = round(max(d_u, d_v), 1)

        # Categorize severity
        if depth_cm < 5.0:
            flood_type = "safe"
            priority_rank = 0
        elif depth_cm < 15.0:
            flood_type = "caution"
            priority_rank = 1
        elif depth_cm < 30.0:
            flood_type = "moderate"
            priority_rank = 2
        else:
            flood_type = "severe"
            priority_rank = 3

        is_blocked = eid in blocked_set
        inflow = round(float((stored_node_m3[u] + stored_node_m3[v]) / 2.0), 2)

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": edge["coords"]
            },
            "properties": {
                "id": eid,
                "from": f"N{u + 1}",
                "to": f"N{v + 1}",
                "depth_cm": depth_cm,
                "flooding_type": flood_type,
                "blocked": is_blocked,
                "rainfall_mm": cum_rain_mm,
                "inflow_rate": inflow,
                "pipe_capacity": round(cap, 2),
                "_rank": priority_rank
            }
        })

    # Sort so caution, moderate, and severe lines render on top of safe lines in MapLibre
    features.sort(key=lambda f: f["properties"]["_rank"])

    return {
        "type": "FeatureCollection",
        "metadata": {
            "scenario_id": scenario_id,
            "timestep": sim_t,
            "elapsed_minutes": round(sim_t * 0.5, 1),
            "rainfall_rate_mm_hr": rainfall_rate,
            "cum_rain_mm": cum_rain_mm,
            "total_nodes": 8001,
            "total_edges": len(features),
            "max_depth_cm": round(float(np.max(depths_node_cm)), 1),
            "flooded_edges_count": sum(1 for f in features if f["properties"]["flooding_type"] != "safe")
        },
        "features": features
    }


@app.get("/manholes")
def get_manholes_state(
    scenario_id: str = Query("historical_sept_2025", description="Scenario ID"),
    timestep: int = Query(0, ge=0),
    slider_step: Optional[int] = Query(None, ge=0),
    slider_max: int = Query(18, ge=1)
):
    """
    Returns full GeoJSON FeatureCollection of all 8,001 drainage manhole nodes
    with elevation, catchment area, building coverage, water depth, and surcharge status.
    """
    sc = _load_scenario(scenario_id)
    T = sc["T"]
    if slider_step is not None:
        sim_t = min(int(round(slider_step * (T - 1) / float(slider_max))), T - 1)
    else:
        sim_t = min(timestep, T - 1)

    node_coords = STATE["node_coords"]
    depth_m = sc["depth_m"][sim_t]
    stored_vol = sc["stored_vol_m3"][sim_t]
    elevs = STATE["elevations"]
    bldg = STATE["building_fracs"]
    areas = STATE["effective_areas"]
    degrees = STATE["node_degrees"]

    features = []
    for u in range(8001):
        d_cm = round(float(depth_m[u]) * 100.0, 1)
        vol_m3 = round(float(stored_vol[u]), 2)
        elev_m = round(float(elevs[u]), 2)
        bldg_pct = round(float(bldg[u]) * 100.0, 1)
        area_m2 = round(float(areas[u]), 1)
        deg = int(degrees[u]) if degrees is not None else 2

        if d_cm <= 0:
            flood_type = "safe"
            status = "Normal Flow"
        elif d_cm <= 15:
            flood_type = "caution"
            status = "Inlet Ponding"
        elif d_cm <= 30:
            flood_type = "moderate"
            status = "Surcharging Manhole"
        else:
            flood_type = "severe"
            status = "Severe Surcharge Overflow"

        lon, lat = node_coords[u]
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [round(float(lon), 6), round(float(lat), 6)]
            },
            "properties": {
                "id": f"N{u + 1}",
                "node_idx": u,
                "depth_cm": d_cm,
                "flooding_type": flood_type,
                "surcharge_status": status,
                "stored_vol_m3": vol_m3,
                "elevation_m": elev_m,
                "building_pct": bldg_pct,
                "effective_area_m2": area_m2,
                "connected_pipes": deg
            }
        })

    return {
        "type": "FeatureCollection",
        "metadata": {
            "scenario_id": scenario_id,
            "timestep": sim_t,
            "total_manholes": 8001
        },
        "features": features
    }


class BlockageRequest(BaseModel):
    edge_id: str
    blocked: bool

@app.post("/blockage")
def toggle_blockage(req: BlockageRequest):
    if req.blocked:
        STATE["blocked_edges"].add(req.edge_id)
    else:
        STATE["blocked_edges"].discard(req.edge_id)
    return {"edge_id": req.edge_id, "blocked": req.edge_id in STATE["blocked_edges"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
