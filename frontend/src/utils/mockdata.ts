import { ROAD_NODES, ROAD_EDGES } from "../data/roadNetwork";
import { getFloodingType } from "./waterDepthLabel";
import type { RoadGeoJSON, ScenarioInfo, ManholeGeoJSON } from "../types/flood";

const isRemoteHttps =
  typeof window !== "undefined" &&
  window.location.protocol === "https:" &&
  !import.meta.env.VITE_API_URL;

const API_BASE = import.meta.env.VITE_API_URL || (isRemoteHttps ? "" : "http://localhost:8000");

export const HISTORICAL_SCENARIOS: ScenarioInfo[] = [
  {
    id: "historical_sept_2025",
    name: "Kolkata Cloudburst (Sept 2025)",
    category: "Historical Storm",
    description: "High-intensity 98mm/hr cloudburst inundating Jadavpur & Southern Kolkata.",
    timesteps: 721,
    duration_hours: 6.0,
    peak_intensity_mm_hr: 98.0,
  },
  {
    id: "historical_2021",
    name: "Cyclone Yaas Inundation (May 2021)",
    category: "Historical Storm",
    description: "Severe cyclonic depression causing prolonged tidal-monsoon urban flooding.",
    timesteps: 841,
    duration_hours: 7.0,
    peak_intensity_mm_hr: 98.0,
  },
];

interface ScenarioStepData {
  step: number;
  sim_t: number;
  rain_rate: number;
  cum_rain: number;
  depth_cm: number[];
  stored_m3: number[];
}

interface ScenarioPayload {
  id: string;
  name: string;
  category: string;
  description: string;
  timesteps: number;
  duration_hours: number;
  peak_intensity_mm_hr: number;
  steps: ScenarioStepData[];
}

interface StaticNodesPayload {
  elev_m: number[];
  bldg_pct: number[];
  area_m2: number[];
  connected_pipes: number[];
}

// In-memory caches for static scenario JSON
const scenarioCache: Partial<Record<string, Promise<ScenarioPayload | null>>> = {};
let staticNodesPromise: Promise<StaticNodesPayload | null> | null = null;
const cachedRoadData: Record<string, RoadGeoJSON> = {};
const cachedManholeData: Record<string, ManholeGeoJSON> = {};

// Fast node lookup index
const nodeById = Object.fromEntries(ROAD_NODES.map((n) => [n.id, n]));

// Helper to load static node attributes (elevation, building %, drainage area)
async function loadStaticNodes(): Promise<StaticNodesPayload | null> {
  if (staticNodesPromise) return staticNodesPromise;
  staticNodesPromise = fetch("/data/static_nodes.json")
    .then((r) => (r.ok ? r.json() : null))
    .catch((err) => {
      console.warn("Could not load static_nodes.json:", err);
      return null;
    });
  return staticNodesPromise;
}

// Helper to load pre-baked hydrodynamic scenario JSON from public/data/
async function loadScenarioData(scenarioId: string): Promise<ScenarioPayload | null> {
  const existing = scenarioCache[scenarioId];
  if (existing) {
    return existing;
  }
  const promise = fetch(`/data/${scenarioId}.json`)
    .then((r) => (r.ok ? r.json() : null))
    .catch((err) => {
      console.warn(`Could not load scenario ${scenarioId}.json:`, err);
      return null;
    });
  scenarioCache[scenarioId] = promise;
  return promise;
}

export async function fetchAvailableScenarios(): Promise<ScenarioInfo[]> {
  if (!API_BASE) {
    return HISTORICAL_SCENARIOS;
  }
  try {
    const res = await fetch(`${API_BASE}/scenarios`);
    if (!res.ok) throw new Error(`API error ${res.status}`);
    const data = await res.json();
    return data.scenarios;
  } catch (err) {
    console.warn("Using historical scenario definitions:", err);
    return HISTORICAL_SCENARIOS;
  }
}

export async function fetchRealRoadFloodData(
  timestepIndex: number,
  blockedRoadIds: Set<string>,
  scenarioId: string = "historical_sept_2025"
): Promise<RoadGeoJSON> {
  const cacheKey = `${scenarioId}_${timestepIndex}`;

  // If live backend API is available, try fetching live
  if (API_BASE) {
    try {
      const res = await fetch(
        `${API_BASE}/flood-state?scenario_id=${scenarioId}&slider_step=${timestepIndex}&slider_max=18`
      );
      if (res.ok) {
        const data: RoadGeoJSON = await res.json();
        if (blockedRoadIds && blockedRoadIds.size > 0) {
          data.features.forEach((f) => {
            if (blockedRoadIds.has(f.properties.id)) {
              f.properties.blocked = true;
            }
          });
        }
        cachedRoadData[cacheKey] = data;
        return data;
      }
    } catch {
      // Fallback to static scenario data
    }
  }

  // Load from pre-baked hydrodynamic scenario JSON
  if (cachedRoadData[cacheKey]) {
    const data = cachedRoadData[cacheKey];
    if (blockedRoadIds && blockedRoadIds.size > 0) {
      data.features.forEach((f) => {
        f.properties.blocked = blockedRoadIds.has(f.properties.id);
      });
    }
    return data;
  }

  const scData = await loadScenarioData(scenarioId);
  const step = scData?.steps?.[Math.min(timestepIndex, (scData.steps?.length ?? 1) - 1)];

  const features = ROAD_EDGES.map((edge, i) => {
    const baseCap = +(0.6 + (i % 5) * 0.3).toFixed(2);
    let depth = 0;
    let inflow = 0;
    let rainfall = 0;

    if (step && step.depth_cm) {
      const u = parseInt(edge.from.slice(1), 10) - 1;
      const v = parseInt(edge.to.slice(1), 10) - 1;
      const d_u = step.depth_cm[u] ?? 0;
      const d_v = step.depth_cm[v] ?? 0;
      depth = Math.round(Math.max(d_u, d_v) * 10) / 10;
      if (step.stored_m3) {
        inflow = Math.round(((step.stored_m3[u] + step.stored_m3[v]) / 2) * 100) / 100;
      }
      rainfall = step.cum_rain ?? step.rain_rate ?? 0;
    } else {
      // Fallback mathematical simulation if JSON not loaded
      const factor = Math.sin((timestepIndex / 18) * Math.PI);
      inflow = +(baseCap * factor * 1.8).toFixed(2);
      depth = Math.max(0, Math.round((inflow - baseCap) * 35));
      rainfall = +(factor * 45).toFixed(1);
    }

    const from = nodeById[edge.from];
    const to = nodeById[edge.to];

    return {
      type: "Feature" as const,
      geometry: {
        type: "LineString" as const,
        coordinates: [
          [from.lng, from.lat],
          ...(edge.path ?? []),
          [to.lng, to.lat],
        ] as [number, number][],
      },
      properties: {
        id: edge.id,
        from: edge.from,
        to: edge.to,
        depth_cm: depth,
        flooding_type: getFloodingType(depth),
        blocked: blockedRoadIds.has(edge.id),
        rainfall_mm: rainfall,
        inflow_rate: inflow,
        pipe_capacity: baseCap,
      },
    };
  });

  const collection: RoadGeoJSON = { type: "FeatureCollection", features };
  cachedRoadData[cacheKey] = collection;
  return collection;
}

export async function fetchRealManholesData(
  timestepIndex: number,
  scenarioId: string = "historical_sept_2025"
): Promise<ManholeGeoJSON> {
  const cacheKey = `${scenarioId}_${timestepIndex}`;
  if (cachedManholeData[cacheKey]) {
    return cachedManholeData[cacheKey];
  }

  // If live backend API is available, try fetching live
  if (API_BASE) {
    try {
      const res = await fetch(
        `${API_BASE}/manholes?scenario_id=${scenarioId}&slider_step=${timestepIndex}&slider_max=18`
      );
      if (res.ok) {
        const data: ManholeGeoJSON = await res.json();
        cachedManholeData[cacheKey] = data;
        return data;
      }
    } catch {
      // Fallback to static scenario data
    }
  }

  // Load ground-truth scenario and static graph properties
  const [scData, staticNodes] = await Promise.all([
    loadScenarioData(scenarioId),
    loadStaticNodes(),
  ]);

  const step = scData?.steps?.[Math.min(timestepIndex, (scData.steps?.length ?? 1) - 1)];

  const features = ROAD_NODES.map((n, i) => {
    let depth = 0;
    let storedVol = 0;
    let elev = staticNodes?.elev_m?.[i] ?? +(7.5 + (i % 10) * 0.35).toFixed(2);
    let bldg = staticNodes?.bldg_pct?.[i] ?? 68.5;
    let area = staticNodes?.area_m2?.[i] ?? 2450.0;
    let connectedPipes = staticNodes?.connected_pipes?.[i] ?? 3;

    if (step && step.depth_cm) {
      depth = Math.round((step.depth_cm[i] ?? 0) * 10) / 10;
      storedVol = Math.round((step.stored_m3?.[i] ?? 0) * 100) / 100;
    } else {
      const factor = Math.sin((timestepIndex / 18) * Math.PI);
      depth = Math.max(0, Math.round(factor * 35 - (i % 7) * 4));
      storedVol = +(depth * 0.08).toFixed(2);
    }

    let status = "Normal Flow";
    let flood_type: "safe" | "caution" | "moderate" | "severe" = "safe";

    if (depth > 30) {
      status = "Severe Surcharge Overflow";
      flood_type = "severe";
    } else if (depth > 15) {
      status = "Surcharging Manhole";
      flood_type = "moderate";
    } else if (depth > 0) {
      status = "Inlet Ponding";
      flood_type = "caution";
    }

    return {
      type: "Feature" as const,
      geometry: {
        type: "Point" as const,
        coordinates: [n.lng, n.lat] as [number, number],
      },
      properties: {
        id: n.id,
        node_idx: i,
        depth_cm: depth,
        flooding_type: flood_type,
        surcharge_status: status,
        stored_vol_m3: storedVol,
        elevation_m: elev,
        building_pct: bldg,
        effective_area_m2: area,
        connected_pipes: connectedPipes,
      },
    };
  });

  const collection: ManholeGeoJSON = { type: "FeatureCollection", features };
  cachedManholeData[cacheKey] = collection;
  return collection;
}

// Fallback synchronous generators (for routing initialization before async loads)
export function getMockRoadFloodData(
  timestepIndex: number,
  blockedRoadIds: Set<string>
): RoadGeoJSON {
  const factor = Math.sin((timestepIndex / 18) * Math.PI);
  const features = ROAD_EDGES.map((edge, i) => {
    const baseCap = 0.6 + (i % 5) * 0.3;
    const inflow = +(baseCap * factor * 1.8).toFixed(2);
    const depth = Math.max(0, Math.round((inflow - baseCap) * 35));
    const from = nodeById[edge.from];
    const to = nodeById[edge.to];

    return {
      type: "Feature" as const,
      geometry: {
        type: "LineString" as const,
        coordinates: [
          [from.lng, from.lat],
          ...(edge.path ?? []),
          [to.lng, to.lat],
        ] as [number, number][],
      },
      properties: {
        id: edge.id,
        from: edge.from,
        to: edge.to,
        depth_cm: depth,
        flooding_type: getFloodingType(depth),
        blocked: blockedRoadIds.has(edge.id),
        rainfall_mm: +(factor * 45).toFixed(1),
        inflow_rate: inflow,
        pipe_capacity: baseCap,
      },
    };
  });

  return { type: "FeatureCollection", features };
}

export function getMockManholesData(timestepIndex: number): ManholeGeoJSON {
  const factor = Math.sin((timestepIndex / 18) * Math.PI);
  const features = ROAD_NODES.map((n, i) => {
    const elev = +(7.5 + (i % 10) * 0.35).toFixed(2);
    const depth = Math.max(0, Math.round(factor * 35 - (i % 7) * 4));
    let status = "Normal Flow";
    let flood_type: "safe" | "caution" | "moderate" | "severe" = "safe";
    if (depth > 30) {
      status = "Severe Surcharge Overflow";
      flood_type = "severe";
    } else if (depth > 15) {
      status = "Surcharging Manhole";
      flood_type = "moderate";
    } else if (depth > 0) {
      status = "Inlet Ponding";
      flood_type = "caution";
    }

    return {
      type: "Feature" as const,
      geometry: {
        type: "Point" as const,
        coordinates: [n.lng, n.lat] as [number, number],
      },
      properties: {
        id: n.id,
        node_idx: i,
        depth_cm: depth,
        flooding_type: flood_type,
        surcharge_status: status,
        stored_vol_m3: +(depth * 0.08).toFixed(2),
        elevation_m: elev,
        building_pct: 68.5,
        effective_area_m2: 2450.0,
        connected_pipes: 3,
      },
    };
  });

  return { type: "FeatureCollection", features };
}