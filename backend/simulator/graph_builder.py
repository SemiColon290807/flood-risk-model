"""
graph_builder.py — Drainage-graph constructor for VectorizedSimulationEngine.

Input files (in ../data/):
    roads_ju.json   — Raw Overpass API JSON (nodes + ways with highway tags)
    dem_ju.tif      — SRTM GL1 GeoTIFF, EPSG:4326

Outputs a dict containing the arrays that VectorizedSimulationEngine.__init__
expects:
    elevations      — 1-D float64, per node (metres, from DEM)
    areas           — 1-D float64, per node (tributary catchment area, m²)
    pipe_edges      — (E, 2) int32, from → to node indices
    pipe_diameters  — 1-D float64, per edge (metres)
    pipe_slopes     — 1-D float64, per edge (dimensionless)

Citation for diameter table:
    CPHEEO, *Manual on Storm Water Drainage Systems*, 1st Ed., 2019,
    Ministry of Housing & Urban Affairs, Government of India.
    Standard sizes: 300/450/600/750/900/1050/1200/1500/1800/2000 mm.
    Minimum pipe diameter: 300 mm (§ 3.2.1).
    Design return periods by road class: 2–5 yr residential,
    5–10 yr commercial, 10–25 yr arterial (Table 3.1).
"""

import json
import pathlib
import numpy as np

# ── Optional heavy imports (installed separately) ──────────────────────
try:
    import rasterio
    from rasterio.transform import rowcol
except ImportError:
    rasterio = None

try:
    from pyproj import Transformer
except ImportError:
    Transformer = None


# ───────────────────────────────────────────────────────────────────────
# 1.  Constants
# ───────────────────────────────────────────────────────────────────────

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"

# CPHEEO-standard pipe diameters mapped to OSM highway tags.
# Footways/paths/steps/pedestrian are excluded — drains follow carriageways.
HIGHWAY_DIAMETER_M = {
    "primary":        0.900,
    "primary_link":   0.900,
    "secondary":      0.750,
    "secondary_link": 0.750,
    "tertiary":       0.600,
    "tertiary_link":  0.600,
    "residential":    0.450,
    "unclassified":   0.450,
    "service":        0.300,
    "living_street":  0.300,
    "track":          0.300,
}

# Highway tags to exclude entirely (non-vehicular — no drain)
EXCLUDED_HIGHWAY = {"footway", "path", "steps", "pedestrian", "cycleway",
                    "bridleway", "corridor", "proposed", "construction"}

# Manning's n for concrete storm drains (conservative, Indian maintenance)
DEFAULT_ROUGHNESS = 0.017

# Default tributary area per road-graph node (m²).
# This is overridden later if you build the surface grid and Voronoi/Thiessen
# allocation; for now, each intersection gets a ~40 m radius catchment.
DEFAULT_CATCHMENT_AREA_M2 = 40.0 * 40.0  # 1 600 m²

# Elevation outlier clamp — SRTM artefact protection (see DEM analysis)
ELEV_CLIP_MIN = -5.0   # m  (sea level delta)
ELEV_CLIP_MAX = 30.0   # m  (real terrain upper bound for JU zone)


# ───────────────────────────────────────────────────────────────────────
# 2.  Overpass JSON → node dict and filtered way list
# ───────────────────────────────────────────────────────────────────────

def _load_overpass_roads(path=None):
    """Return {osm_id: (lat, lon)} and [way_dicts] from Overpass JSON."""
    path = path or DATA_DIR / "roads_ju.json"
    with open(path) as f:
        raw = json.load(f)

    nodes = {}          # osm_id → (lat, lon)
    ways = []           # list of way dicts with highway tag

    for elem in raw["elements"]:
        if elem["type"] == "node":
            nodes[elem["id"]] = (elem["lat"], elem["lon"])
        elif elem["type"] == "way":
            tags = elem.get("tags", {})
            hw = tags.get("highway")
            if hw and hw not in EXCLUDED_HIGHWAY and hw in HIGHWAY_DIAMETER_M:
                ways.append(elem)

    return nodes, ways


# ───────────────────────────────────────────────────────────────────────
# 3.  Build topology: intersections (manholes) = graph nodes,
#     road segments between intersections = pipe edges
# ───────────────────────────────────────────────────────────────────────

def _haversine_m(lat1, lon1, lat2, lon2):
    """Quick haversine distance in metres between two lat/lon points."""
    R = 6_371_000.0  # Earth radius in metres
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = (np.sin(dlat / 2) ** 2 +
         np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) *
         np.sin(dlon / 2) ** 2)
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def _build_raw_graph(osm_nodes, ways):
    """
    Build the drainage graph where:
        - **Nodes** = road intersections (OSM nodes shared by ≥ 2 ways)
          plus dead-end way endpoints.  These represent manhole locations.
        - **Edges** = entire road segments between consecutive intersection
          nodes, with length = sum of polyline segment distances.

    Intermediate polyline vertices (bends, survey points) are collapsed
    into the edge — they contribute to pipe length but are NOT graph nodes.

    Returns
    -------
    unique_ids : list[int]
        Ordered list of OSM node IDs that are intersection/manhole nodes.
    id_to_idx : dict[int, int]
        Mapping from OSM node ID → 0-based graph index.
    edges : list[tuple[int, int, str, float]]
        (from_idx, to_idx, highway_tag, polyline_length_m) for every
        road segment between consecutive intersection nodes.
    """
    # ── Pass 1: count how many ways reference each node ──
    node_way_count = {}  # osm_node_id → number of distinct ways it appears in
    for way in ways:
        seen_in_way = set()
        for nid in way["nodes"]:
            if nid in osm_nodes and nid not in seen_in_way:
                node_way_count[nid] = node_way_count.get(nid, 0) + 1
                seen_in_way.add(nid)

    # ── Identify intersection nodes ──
    # A node is an intersection (manhole) if:
    #   - it appears in ≥ 2 different ways  (road junction), OR
    #   - it is the first or last node of any way  (dead-end / terminal)
    intersection_ids = set()
    for way in ways:
        node_list = [nid for nid in way["nodes"] if nid in osm_nodes]
        if len(node_list) < 2:
            continue
        # Endpoints are always intersections/terminals
        intersection_ids.add(node_list[0])
        intersection_ids.add(node_list[-1])
        # Interior nodes shared by multiple ways
        for nid in node_list[1:-1]:
            if node_way_count.get(nid, 0) >= 2:
                intersection_ids.add(nid)

    unique_ids = sorted(intersection_ids)
    id_to_idx = {nid: i for i, nid in enumerate(unique_ids)}

    # ── Pass 2: walk each way, emit edges between consecutive intersections ──
    edges = []
    for way in ways:
        hw = way["tags"]["highway"]
        node_list = [nid for nid in way["nodes"] if nid in osm_nodes]
        if len(node_list) < 2:
            continue

        # Walk the node list, accumulating polyline distance between
        # consecutive intersection nodes
        seg_start = node_list[0]
        accum_dist = 0.0

        for k in range(1, len(node_list)):
            prev_nid = node_list[k - 1]
            curr_nid = node_list[k]

            # Accumulate segment distance
            lat1, lon1 = osm_nodes[prev_nid]
            lat2, lon2 = osm_nodes[curr_nid]
            accum_dist += _haversine_m(lat1, lon1, lat2, lon2)

            # Emit edge only when we reach the next intersection node
            if curr_nid in intersection_ids and curr_nid != seg_start:
                ia = id_to_idx[seg_start]
                ib = id_to_idx[curr_nid]
                poly_len = max(accum_dist, 1.0)  # floor at 1 m

                # Bidirectional: water can flow either way; slope orients later
                edges.append((ia, ib, hw, poly_len))
                edges.append((ib, ia, hw, poly_len))

                # Reset for next segment
                seg_start = curr_nid
                accum_dist = 0.0

    return unique_ids, id_to_idx, edges


# ───────────────────────────────────────────────────────────────────────
# 4.  Coordinate projection: EPSG:4326 → UTM 45N (EPSG:32645)
# ───────────────────────────────────────────────────────────────────────

def _project_nodes(osm_nodes, unique_ids, src_crs="EPSG:4326",
                   dst_crs="EPSG:32645"):
    """
    Project lat/lon → UTM easting/northing (metres).
    Returns (easting_arr, northing_arr) as float64 arrays aligned with
    unique_ids ordering.
    """
    if Transformer is None:
        raise ImportError("pyproj is required for coordinate projection.  "
                          "Install with:  pip install pyproj")

    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)

    lats = np.array([osm_nodes[nid][0] for nid in unique_ids], dtype=np.float64)
    lons = np.array([osm_nodes[nid][1] for nid in unique_ids], dtype=np.float64)

    # pyproj with always_xy=True expects (x=lon, y=lat) input
    eastings, northings = transformer.transform(lons, lats)
    return eastings, northings


# ───────────────────────────────────────────────────────────────────────
# 5.  DEM elevation sampling
# ───────────────────────────────────────────────────────────────────────

def _sample_dem(osm_nodes, unique_ids, dem_path=None):
    """
    Sample the DEM at each graph node's lat/lon position.
    Clips extreme outliers (SRTM artefacts) and replaces nodata with the
    neighbourhood median.
    """
    dem_path = dem_path or DATA_DIR / "dem_ju.tif"

    if rasterio is None:
        raise ImportError("rasterio is required for DEM sampling.  "
                          "Install with:  pip install rasterio")

    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype(np.float64)
        transform = src.transform
        nodata = src.nodata
        nrows, ncols = dem.shape

    # Replace nodata pixels with NaN for safe statistics
    if nodata is not None:
        dem[dem == nodata] = np.nan

    elevations = np.empty(len(unique_ids), dtype=np.float64)

    for i, nid in enumerate(unique_ids):
        lat, lon = osm_nodes[nid]
        # rowcol returns (row, col) from the dataset's affine transform
        row, col = rowcol(transform, lon, lat)
        # Clamp to raster bounds
        row = max(0, min(row, nrows - 1))
        col = max(0, min(col, ncols - 1))
        elevations[i] = dem[row, col]

    # ── Outlier handling ──
    # Replace NaN (nodata nodes) with local median of valid values
    valid_mask = np.isfinite(elevations)
    if not np.all(valid_mask):
        median_elev = np.nanmedian(elevations)
        elevations[~valid_mask] = median_elev

    # Clip SRTM artefacts (e.g. the suspicious 47 m pixel)
    elevations = np.clip(elevations, ELEV_CLIP_MIN, ELEV_CLIP_MAX)

    return elevations


# ───────────────────────────────────────────────────────────────────────
# 6.  Compute pipe slopes from sampled elevations and polyline distances
# ───────────────────────────────────────────────────────────────────────

def _compute_slopes_and_orient(edges, elevations, eastings, northings):
    """
    For each edge (from_idx, to_idx, highway_tag, polyline_length_m):
        1. Use the pre-computed polyline length (accumulated along
           intermediate nodes) rather than straight-line distance.
        2. Compute slope = abs(Δz) / polyline_length.
        3. Orient the edge downhill: from = higher-elevation node,
           to = lower-elevation node.  (If flat, keep original order.)

    Returns
    -------
    oriented_edges : np.ndarray, shape (E, 2), int32
    pipe_diameters : np.ndarray, shape (E,), float64
    pipe_slopes    : np.ndarray, shape (E,), float64
    edge_lengths_m : np.ndarray, shape (E,), float64
    """
    n_edges = len(edges)
    oriented = np.empty((n_edges, 2), dtype=np.int32)
    diameters = np.empty(n_edges, dtype=np.float64)
    slopes = np.empty(n_edges, dtype=np.float64)
    lengths = np.empty(n_edges, dtype=np.float64)

    for k, (i, j, hw, poly_len) in enumerate(edges):
        dz = elevations[i] - elevations[j]  # positive = i is higher

        # Orient downhill
        if dz >= 0:
            oriented[k] = [i, j]
        else:
            oriented[k] = [j, i]

        slopes[k] = abs(dz) / poly_len
        diameters[k] = HIGHWAY_DIAMETER_M.get(hw, 0.300)
        lengths[k] = poly_len

    return oriented, diameters, slopes, lengths


# ───────────────────────────────────────────────────────────────────────
# 7.  De-duplicate edges: keep the larger-diameter pipe if two ways
#     share a segment, collapse reversed duplicates.
# ───────────────────────────────────────────────────────────────────────

def _dedup_edges(oriented, diameters, slopes, lengths):
    """
    If the same (from, to) pair appears more than once (because two OSM
    ways share a road segment, or because we created both directions),
    keep only the entry with the largest diameter.

    Returns filtered arrays of the same types.
    """
    best = {}  # (from, to) → index into arrays
    for k in range(len(oriented)):
        key = (oriented[k, 0], oriented[k, 1])
        if key not in best or diameters[k] > diameters[best[key]]:
            best[key] = k

    keep = sorted(best.values())
    return oriented[keep], diameters[keep], slopes[keep], lengths[keep]


# ───────────────────────────────────────────────────────────────────────
# 8.  Public API
# ───────────────────────────────────────────────────────────────────────

def build_drainage_graph(roads_path=None, dem_path=None, verbose=True):
    """
    End-to-end pipeline: parse Overpass JSON + DEM → arrays ready for
    VectorizedSimulationEngine.

    Parameters
    ----------
    roads_path : str or Path, optional
        Path to roads_ju.json.  Defaults to ../data/roads_ju.json.
    dem_path : str or Path, optional
        Path to dem_ju.tif.  Defaults to ../data/dem_ju.tif.
    verbose : bool
        Print progress and summary statistics.

    Returns
    -------
    dict with keys:
        elevations      np.ndarray (N,)     metres
        areas           np.ndarray (N,)     m² (default catchment)
        pipe_edges      np.ndarray (E, 2)   int32 node indices
        pipe_diameters  np.ndarray (E,)     metres
        pipe_slopes     np.ndarray (E,)     dimensionless
        pipe_lengths_m  np.ndarray (E,)     metres (for reference)
        eastings        np.ndarray (N,)     UTM easting (m)
        northings       np.ndarray (N,)     UTM northing (m)
        osm_ids         list[int]           OSM node IDs (same order as indices)
    """
    if verbose:
        print("[graph_builder] Loading Overpass roads JSON …")
    osm_nodes, ways = _load_overpass_roads(roads_path)
    if verbose:
        print(f"  {len(osm_nodes):,} OSM nodes, {len(ways):,} ways "
              f"after filtering excluded highway types")

    if verbose:
        print("[graph_builder] Building raw topology …")
    unique_ids, id_to_idx, edges = _build_raw_graph(osm_nodes, ways)
    n_nodes = len(unique_ids)
    if verbose:
        print(f"  {n_nodes:,} graph nodes, {len(edges):,} raw directed edges")

    if verbose:
        print("[graph_builder] Projecting to UTM 45N (EPSG:32645) …")
    eastings, northings = _project_nodes(osm_nodes, unique_ids)

    if verbose:
        print("[graph_builder] Sampling DEM elevations …")
    elevations = _sample_dem(osm_nodes, unique_ids, dem_path)
    if verbose:
        print(f"  Elevation range after clipping: "
              f"{elevations.min():.1f} – {elevations.max():.1f} m, "
              f"mean {elevations.mean():.1f} m")

    if verbose:
        print("[graph_builder] Computing slopes and orienting edges downhill …")
    oriented, diameters, slopes, lengths = _compute_slopes_and_orient(
        edges, elevations, eastings, northings
    )

    if verbose:
        print("[graph_builder] De-duplicating edges …")
    oriented, diameters, slopes, lengths = _dedup_edges(
        oriented, diameters, slopes, lengths
    )
    if verbose:
        print(f"  {len(oriented):,} edges after de-duplication")

    # Default catchment areas (uniform for now — override with Voronoi later)
    areas = np.full(n_nodes, DEFAULT_CATCHMENT_AREA_M2, dtype=np.float64)

    # ── Summary stats ──
    if verbose:
        unique_diams = np.unique(diameters)
        print("\n  Pipe diameter distribution:")
        for d in sorted(unique_diams):
            count = np.sum(diameters == d)
            print(f"    {d*1000:.0f} mm : {count:,} edges")
        flat_frac = np.mean(slopes < 1e-4) * 100
        print(f"\n  Slope stats: min={slopes.min():.6f}, "
              f"max={slopes.max():.4f}, "
              f"mean={slopes.mean():.5f}, "
              f"flat (<1e-4): {flat_frac:.1f}%")
        print(f"  Edge length stats: min={lengths.min():.1f} m, "
              f"max={lengths.max():.1f} m, "
              f"mean={lengths.mean():.1f} m")
        print(f"\n[graph_builder] Done — {n_nodes:,} nodes, "
              f"{len(oriented):,} edges ready for VectorizedSimulationEngine.")

    return {
        "elevations":     elevations,
        "areas":          areas,
        "pipe_edges":     oriented,
        "pipe_diameters": diameters,
        "pipe_slopes":    slopes,
        "pipe_lengths_m": lengths,
        "eastings":       eastings,
        "northings":      northings,
        "osm_ids":        unique_ids,
    }


# ───────────────────────────────────────────────────────────────────────
# 9.  CLI: quick-test when run directly
# ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = build_drainage_graph()
    print(f"\n── Quick check ──")
    print(f"elevations shape:     {result['elevations'].shape}")
    print(f"areas shape:          {result['areas'].shape}")
    print(f"pipe_edges shape:     {result['pipe_edges'].shape}")
    print(f"pipe_diameters shape: {result['pipe_diameters'].shape}")
    print(f"pipe_slopes shape:    {result['pipe_slopes'].shape}")
