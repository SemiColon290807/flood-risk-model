"""
surface_grid.py — Dense surface sheet-flow grid constructor for
VectorizedSimulationEngine (Section 11 of the project spec).

This is the DENSE grid (uniform cells, ~40 m spacing) that Phase 1
(rainfall) and Phase 4 (2D sheet-flow redistribution) of kinematic_sim.py
operate on — distinct from the SPARSE drainage graph (manholes/pipes)
built by graph_builder.py (8,001 nodes, 14,344 edges for the JU zone).

Depends on the dict returned by graph_builder.build_drainage_graph() for
manhole positions (eastings/northings) — call that first.

── Spatial coupling (Section 14) ───────────────────────────────────────
Grid-cell containment and uncapped nearest-neighbor were both rejected:
    - Containment: manhole spacing (~44m) is close to cell size (40m),
      so cells often contain 0 or several manholes — no clean rule.
    - Uncapped nearest-neighbor: a cell far from any road would still be
      assigned a "nearest" manhole and could drain directly into the pipe
      network, skipping physical overland sheet flow entirely.
Fix: distance-capped KD-tree assignment. Every cell still gets a nearest
manhole (used for Thiessen catchment-area bookkeeping), but only cells
within INLET_DIST_THRESHOLD_M actually get direct Phase-2 inlet drainage
(has_inlet=True). Farther cells must reach an inlet-enabled cell via
Phase 4 lateral sheet flow first, same as water actually has to.

── Building treatment (Section 15) ─────────────────────────────────────
Dual-porosity formulation (mathematically equivalent to MIKE FLOOD/DHI's
approach — see citations below), NOT a boolean mask + elevation bump:
    - building_fraction: continuous 0..1 footprint coverage per cell,
      from area-weighted (supersampled) rasterization.
    - effective_area  = cell_area * (1 - building_fraction)       — same
      rainfall volume concentrates into less open ground.
    - effective_width  = cell_size * min(1-frac_i, 1-frac_j)       — per
      neighbor pair, buildings constrict (not just block) sheet flow.
    - C_cell = building_fraction*0.92 + (1-building_fraction)*0.35 — a
      spatially-varying runoff coefficient replacing the flat constant.

Citations:
    CPHEEO (2019), Manual on Storm Water Drainage Systems, MoHUA, GoI.
    Schubert, J.E. & Sanders, B.F. (2012), "Building treatments for urban
        flood inundation models", Advances in Water Resources, 41, 49-64.
    DHI (2022), MIKE+ 2D Overland Flow User Guide & Porosity Formulations.
    Rossman, L.A. & Huber, W.C. (2016), SWMM Reference Manual Vol. I —
        Hydrology, EPA/600/R-15/162A.

Input files (in ../data/):
    buildings_ju.json — Raw Overpass API JSON (nodes + closed-ring ways,
                         tagged building=*)
    dem_ju.tif         — SRTM GL1 GeoTIFF, EPSG:4326 (same file used by
                         graph_builder.py)
"""

import json
import pathlib
import numpy as np

try:
    import rasterio
    from rasterio.transform import rowcol, from_origin
    from rasterio.features import rasterize
except ImportError:
    rasterio = None

try:
    from pyproj import Transformer
except ImportError:
    Transformer = None

try:
    from scipy.spatial import cKDTree
except ImportError:
    cKDTree = None

# Reuse the same constants graph_builder.py uses, so DEM sampling and
# outlier handling stay consistent between the two node sets.
from graph_builder import DATA_DIR, ELEV_CLIP_MIN, ELEV_CLIP_MAX


# ───────────────────────────────────────────────────────────────────────
# 1.  Constants
# ───────────────────────────────────────────────────────────────────────

CELL_SIZE_M = 40.0  # confirmed grid resolution

# Section 14.4: distance cap for direct surface->manhole inlet drainage.
# Basis: CPHEEO (2019) mandates 30-50m manhole spacing on straight urban
# pipe runs; the built JU graph's mean edge length is 44.4m; the cell-to-
# nearest-manhole distance distribution shows a sharp natural break
# between P50 (~42m, road-adjacent fabric) and P75 (~154m, open land).
INLET_DIST_THRESHOLD_M = 50.0

# Supersampling factor for area-weighted building_fraction rasterization
# (40m / 8 = 5m sub-pixels — fine enough for an accurate coverage
# fraction without a per-cell polygon-area computation).
BUILDING_SUPERSAMPLE = 8

# Section 15.2: spatially-varying runoff coefficient endpoints.
C_ROOFTOP = 0.92   # near-zero infiltration
C_PERVIOUS = 0.35  # open/pervious ground

# Safety floor: a small number of cells can rasterize to
# building_fraction == 1.0 exactly (e.g. a stadium/large building fully
# spanning a 40m cell), which would make effective_area == 0 and break
# every downstream division (lateral-transfer equalization cap, etc.).
# Even a fully-built footprint has some gutter/gap/alley space in
# reality, so cap the fraction used for effective_area at 98% — keeps
# every consumer numerically safe without needing its own defensive
# clip. Raw building_fraction (used for reporting/c_cell) is left
# unmodified.
MAX_BUILDING_FRACTION_FOR_AREA = 0.98

SRC_CRS = "EPSG:4326"
DST_CRS = "EPSG:32645"  # UTM 45N — same zone graph_builder.py projects into

EXCLUDED_BUILDING_TAGS = {"no"}  # explicitly NOT a building, per OSM convention


# ───────────────────────────────────────────────────────────────────────
# 2.  Grid extent: derive directly from the DEM's own bounds, so the
#     surface grid and DEM sampling are always in agreement.
# ───────────────────────────────────────────────────────────────────────

def _grid_extent_from_dem(dem_path, cell_size_m):
    if rasterio is None:
        raise ImportError("rasterio is required. pip install rasterio")
    if Transformer is None:
        raise ImportError("pyproj is required. pip install pyproj")

    with rasterio.open(dem_path) as src:
        b = src.bounds

    transformer = Transformer.from_crs(SRC_CRS, DST_CRS, always_xy=True)
    xs, ys = transformer.transform(
        [b.left, b.right, b.left, b.right],
        [b.top, b.top, b.bottom, b.bottom],
    )
    west_m, east_m = min(xs), max(xs)
    south_m, north_m = min(ys), max(ys)

    n_cols = int(np.floor((east_m - west_m) / cell_size_m))
    n_rows = int(np.floor((north_m - south_m) / cell_size_m))

    return west_m, north_m, n_rows, n_cols


# ───────────────────────────────────────────────────────────────────────
# 3.  Cell centroid coordinates
# ───────────────────────────────────────────────────────────────────────

def _cell_centroids(west_m, north_m, n_rows, n_cols, cell_size_m):
    """Row 0 = northernmost row, Col 0 = westernmost column."""
    row_idx, col_idx = np.meshgrid(np.arange(n_rows), np.arange(n_cols),
                                    indexing="ij")
    row_idx = row_idx.ravel()
    col_idx = col_idx.ravel()

    x_m = west_m + (col_idx + 0.5) * cell_size_m
    y_m = north_m - (row_idx + 0.5) * cell_size_m
    return x_m, y_m, row_idx, col_idx


# ───────────────────────────────────────────────────────────────────────
# 4.  DEM elevation sampling — same method as graph_builder.py
#     (nearest-pixel + clip), applied to grid centroids.
# ───────────────────────────────────────────────────────────────────────

def _sample_dem_at_centroids(x_m, y_m, dem_path):
    if rasterio is None:
        raise ImportError("rasterio is required. pip install rasterio")
    if Transformer is None:
        raise ImportError("pyproj is required. pip install pyproj")

    inv_transformer = Transformer.from_crs(DST_CRS, SRC_CRS, always_xy=True)
    lons, lats = inv_transformer.transform(x_m, y_m)

    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype(np.float64)
        transform = src.transform
        nodata = src.nodata
        nrows, ncols = dem.shape

    if nodata is not None:
        dem[dem == nodata] = np.nan

    elevations = np.empty(len(x_m), dtype=np.float64)
    for i in range(len(x_m)):
        row, col = rowcol(transform, lons[i], lats[i])
        row = max(0, min(row, nrows - 1))
        col = max(0, min(col, ncols - 1))
        elevations[i] = dem[row, col]

    valid_mask = np.isfinite(elevations)
    if not np.all(valid_mask):
        median_elev = np.nanmedian(elevations)
        elevations[~valid_mask] = median_elev

    elevations = np.clip(elevations, ELEV_CLIP_MIN, ELEV_CLIP_MAX)
    return elevations


# ───────────────────────────────────────────────────────────────────────
# 5.  Building fraction — area-weighted via supersampled rasterization
#     (NOT a centroid-containment boolean; Section 15.2 needs a real
#     coverage fraction per cell, e.g. a cell that's 75% building).
# ───────────────────────────────────────────────────────────────────────

def _load_building_polygons_projected(buildings_path):
    """Parse Overpass building ways into UTM-projected polygon rings."""
    with open(buildings_path) as f:
        raw = json.load(f)

    osm_nodes = {}
    for elem in raw["elements"]:
        if elem["type"] == "node":
            osm_nodes[elem["id"]] = (elem["lat"], elem["lon"])

    transformer = Transformer.from_crs(SRC_CRS, DST_CRS, always_xy=True)

    polygons = []
    for elem in raw["elements"]:
        if elem["type"] != "way":
            continue
        tags = elem.get("tags", {})
        btag = tags.get("building")
        if btag is None or btag in EXCLUDED_BUILDING_TAGS:
            continue

        node_ids = elem["nodes"]
        if len(node_ids) < 4 or node_ids[0] != node_ids[-1]:
            continue  # not a closed ring — skip malformed footprint

        lats = np.array([osm_nodes[n][0] for n in node_ids if n in osm_nodes])
        lons = np.array([osm_nodes[n][1] for n in node_ids if n in osm_nodes])
        if len(lats) < 4:
            continue

        xs, ys = transformer.transform(lons, lats)
        ring = list(zip(xs.tolist(), ys.tolist()))
        polygons.append({"type": "Polygon", "coordinates": [ring]})

    return polygons


def _rasterize_building_fraction(polygons, west_m, north_m, n_rows, n_cols,
                                  cell_size_m, supersample):
    """
    Rasterizes buildings at `supersample`x finer resolution than the
    cell grid, then block-averages back down — gives a real coverage
    FRACTION per cell (e.g. 0.75 for a mostly-built cell), not just a
    single centroid-containment bit.
    """
    if rasterio is None:
        raise ImportError("rasterio is required. pip install rasterio")

    if len(polygons) == 0:
        return np.zeros(n_rows * n_cols, dtype=np.float64)

    fine_rows = n_rows * supersample
    fine_cols = n_cols * supersample
    fine_cell_size = cell_size_m / supersample

    transform = from_origin(west_m, north_m, fine_cell_size, fine_cell_size)
    shapes = [(geom, 1) for geom in polygons]

    burned = rasterize(
        shapes,
        out_shape=(fine_rows, fine_cols),
        transform=transform,
        fill=0,
        dtype=np.uint8,
        all_touched=False,
    )

    # Block-average: (n_rows, supersample, n_cols, supersample) -> mean
    # over the two supersample axes gives the fraction covered per cell.
    reshaped = burned.reshape(n_rows, supersample, n_cols, supersample)
    fraction = reshaped.mean(axis=(1, 3)).astype(np.float64)

    return fraction.ravel()  # row-major, matches cell ordering elsewhere


# ───────────────────────────────────────────────────────────────────────
# 6.  4-connectivity neighbor pairs (Section 14 decision — no diagonals)
# ───────────────────────────────────────────────────────────────────────

def _build_neighbor_pairs(n_rows, n_cols):
    """
    Returns (K, 2) int32 array of flat cell-index pairs for every
    orthogonal (N/S/E/W) adjacency. Each pair listed once (i < j);
    kinematic_sim's Phase 4 handles direction via WSE comparison.
    """

    def flat(r, c):
        return r * n_cols + c

    pairs = []
    for r in range(n_rows):
        for c in range(n_cols):
            i = flat(r, c)
            if c + 1 < n_cols:  # east neighbor
                pairs.append((i, flat(r, c + 1)))
            if r + 1 < n_rows:  # south neighbor
                pairs.append((i, flat(r + 1, c)))

    return np.array(pairs, dtype=np.int32)


# ───────────────────────────────────────────────────────────────────────
# 7.  Distance-capped nearest-manhole assignment (Section 14.3)
# ───────────────────────────────────────────────────────────────────────

def _assign_nearest_manhole(cell_x_m, cell_y_m, manhole_eastings, manhole_northings,
                             inlet_threshold_m):
    if cKDTree is None:
        raise ImportError("scipy is required. pip install scipy")

    manhole_points = np.column_stack([manhole_eastings, manhole_northings])
    tree = cKDTree(manhole_points)

    cell_points = np.column_stack([cell_x_m, cell_y_m])
    dist_m, manhole_idx = tree.query(cell_points, k=1)
    manhole_idx = manhole_idx.astype(np.int32)
    dist_m = dist_m.astype(np.float64)

    has_inlet = dist_m <= inlet_threshold_m
    return manhole_idx, dist_m, has_inlet


def _locate_manhole_host_cells(manhole_eastings, manhole_northings,
                               west_m, north_m, n_rows, n_cols, cell_size_m):
    """
    For each manhole, find the exact flat surface-cell index it physically
    sits in. Used during Phase-3 surcharging so backflow spills directly
    onto the manhole's own host cell.
    """
    cols = np.floor((manhole_eastings - west_m) / cell_size_m).astype(np.int32)
    rows = np.floor((north_m - manhole_northings) / cell_size_m).astype(np.int32)
    cols = np.clip(cols, 0, n_cols - 1)
    rows = np.clip(rows, 0, n_rows - 1)
    return (rows * n_cols + cols).astype(np.int32)


def _thiessen_areas(manhole_idx, n_manholes, cell_area_m2):
    """
    catchment_area[u] = count(cells whose nearest manhole is u) * cell_area.
    Uses the FULL assignment (not filtered by has_inlet) — this is a
    bookkeeping/reporting quantity, distinct from which cells actually
    drain directly (has_inlet) vs. via multi-hop sheet flow.
    """
    counts = np.bincount(manhole_idx, minlength=n_manholes)
    return counts.astype(np.float64) * cell_area_m2


# ───────────────────────────────────────────────────────────────────────
# 8.  Public API
# ───────────────────────────────────────────────────────────────────────

def build_surface_grid(drainage_graph, buildings_path=None, dem_path=None,
                        cell_size_m=CELL_SIZE_M,
                        inlet_dist_threshold_m=INLET_DIST_THRESHOLD_M,
                        verbose=True):
    """
    Parameters
    ----------
    drainage_graph : dict
        Return value of graph_builder.build_drainage_graph(). Must
        contain 'eastings', 'northings' (manhole positions, UTM 45N).
    buildings_path, dem_path : str or Path, optional
        Default to ../data/buildings_ju.json and ../data/dem_ju.tif.
    cell_size_m : float
        Grid spacing. Defaults to 40 m.
    inlet_dist_threshold_m : float
        Max cell-to-manhole distance for direct Phase-2 inlet drainage.
        Defaults to 50 m (see Section 14.4 justification).

    Returns
    -------
    dict — see module docstring for the dual-porosity + coupling fields.
    """
    buildings_path = buildings_path or DATA_DIR / "buildings_ju.json"
    dem_path = dem_path or DATA_DIR / "dem_ju.tif"

    if verbose:
        print("[surface_grid] Deriving grid extent from DEM bounds …")
    west_m, north_m, n_rows, n_cols = _grid_extent_from_dem(dem_path, cell_size_m)
    n_cells = n_rows * n_cols
    if verbose:
        print(f"  Grid: {n_rows} rows x {n_cols} cols = {n_cells:,} cells "
              f"@ {cell_size_m:.0f} m")

    if verbose:
        print("[surface_grid] Computing cell centroids …")
    cell_x_m, cell_y_m, row_idx, col_idx = _cell_centroids(
        west_m, north_m, n_rows, n_cols, cell_size_m
    )

    if verbose:
        print("[surface_grid] Sampling DEM elevation per cell …")
    cell_elevations = _sample_dem_at_centroids(cell_x_m, cell_y_m, dem_path)

    if verbose:
        print(f"[surface_grid] Rasterizing building footprints "
              f"({BUILDING_SUPERSAMPLE}x supersampled area-weighting) …")
    polygons = _load_building_polygons_projected(buildings_path)
    building_fraction = _rasterize_building_fraction(
        polygons, west_m, north_m, n_rows, n_cols, cell_size_m, BUILDING_SUPERSAMPLE
    )
    if verbose:
        built_up = building_fraction > 0.0
        print(f"  {len(polygons):,} building polygons loaded; "
              f"{built_up.sum():,} / {n_cells:,} cells have some building "
              f"coverage (mean fraction over those: "
              f"{building_fraction[built_up].mean():.2f})")

    # Section 15.2 — dual-porosity outputs
    area_frac_capped = np.minimum(building_fraction, MAX_BUILDING_FRACTION_FOR_AREA)
    effective_area_m2 = (cell_size_m ** 2) * (1.0 - area_frac_capped)
    c_cell = building_fraction * C_ROOFTOP + (1.0 - building_fraction) * C_PERVIOUS

    if verbose:
        print("[surface_grid] Building 4-connectivity neighbor pairs …")
    neighbor_pairs = _build_neighbor_pairs(n_rows, n_cols)
    frac_i = building_fraction[neighbor_pairs[:, 0]]
    frac_j = building_fraction[neighbor_pairs[:, 1]]
    neighbor_effective_width_m = cell_size_m * np.minimum(1.0 - frac_i, 1.0 - frac_j)
    if verbose:
        print(f"  {len(neighbor_pairs):,} neighbor pairs; "
              f"{np.sum(neighbor_effective_width_m < cell_size_m):,} "
              f"constricted by adjacent building coverage")

    if verbose:
        print(f"[surface_grid] Assigning cells to nearest manhole "
              f"(KD-tree, {inlet_dist_threshold_m:.0f}m inlet cap) …")
    manhole_assignment, manhole_dist_m, has_inlet = _assign_nearest_manhole(
        cell_x_m, cell_y_m,
        drainage_graph["eastings"], drainage_graph["northings"],
        inlet_dist_threshold_m,
    )
    n_manholes = len(drainage_graph["eastings"])
    updated_manhole_areas_m2 = _thiessen_areas(
        manhole_assignment, n_manholes, cell_size_m ** 2
    )
    manhole_host_cell = _locate_manhole_host_cells(
        drainage_graph["eastings"], drainage_graph["northings"],
        west_m, north_m, n_rows, n_cols, cell_size_m
    )

    if verbose:
        pct_inlet = 100.0 * has_inlet.mean()
        p10, p25, p50, p75, p90 = np.percentile(manhole_dist_m, [10, 25, 50, 75, 90])
        print(f"  {has_inlet.sum():,} / {n_cells:,} cells ({pct_inlet:.1f}%) "
              f"have a direct inlet (<= {inlet_dist_threshold_m:.0f}m)")
        print(f"  Distance percentiles — P10:{p10:.0f}m P25:{p25:.0f}m "
              f"P50:{p50:.0f}m P75:{p75:.0f}m P90:{p90:.0f}m")
        old_default = drainage_graph["areas"][0]
        print(f"  Catchment area — old flat default: {old_default:.0f} m^2 "
              f"-> new Thiessen range: {updated_manhole_areas_m2.min():.0f} "
              f"to {updated_manhole_areas_m2.max():.0f} m^2")

    if verbose:
        print(f"\n[surface_grid] Done — {n_cells:,} cells ready for "
              f"VectorizedSimulationEngine's surface phase.")

    return {
        "cell_elevations": cell_elevations,
        "cell_areas_m2": np.full(n_cells, cell_size_m ** 2, dtype=np.float64),
        "cell_effective_area_m2": effective_area_m2,
        "building_fraction": building_fraction,
        "c_cell": c_cell,
        "cell_x_m": cell_x_m,
        "cell_y_m": cell_y_m,
        "row_idx": row_idx,
        "col_idx": col_idx,
        "grid_shape": (n_rows, n_cols),
        "cell_size_m": cell_size_m,
        "neighbor_pairs": neighbor_pairs,
        "neighbor_dist_m": cell_size_m,               # unaffected by porosity
        "neighbor_effective_width_m": neighbor_effective_width_m,  # per-pair now
        "manhole_assignment": manhole_assignment,
        "manhole_assignment_dist_m": manhole_dist_m,
        "manhole_host_cell": manhole_host_cell,
        "has_inlet": has_inlet,
        "inlet_dist_threshold_m": inlet_dist_threshold_m,
        "updated_manhole_areas_m2": updated_manhole_areas_m2,
    }


# ───────────────────────────────────────────────────────────────────────
# 9.  CLI: quick-test when run directly
# ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from graph_builder import build_drainage_graph

    drainage = build_drainage_graph()
    print()
    grid = build_surface_grid(drainage)

    print(f"\n── Quick check ──")
    print(f"grid_shape:                  {grid['grid_shape']}")
    print(f"cell_elevations shape:       {grid['cell_elevations'].shape}")
    print(f"building_fraction range:     {grid['building_fraction'].min():.2f} "
          f"to {grid['building_fraction'].max():.2f}")
    print(f"neighbor_pairs shape:        {grid['neighbor_pairs'].shape}")
    print(f"has_inlet True count:        {grid['has_inlet'].sum():,}")