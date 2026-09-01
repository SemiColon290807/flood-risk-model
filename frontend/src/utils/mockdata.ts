import { ROAD_NODES, ROAD_EDGES } from "../data/roadNetwork";
import { getFloodingType } from "./waterDepthLabel";
import type { RoadGeoJSON, ScenarioInfo, ManholeGeoJSON } from "../types/flood";

const API_BASE = "http://localhost:8000";
const cachedData: Record<string, RoadGeoJSON> = {};

export async function fetchAvailableScenarios(): Promise<ScenarioInfo[]> {
  try {
    const res = await fetch(`${API_BASE}/scenarios`);
    if (!res.ok) throw new Error(`API error ${res.status}`);
    const data = await res.json();
    return data.scenarios;
  } catch (err) {
    console.warn("Using fallback scenario definitions:", err);
    return [
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
  }
}

export async function fetchRealRoadFloodData(
  timestepIndex: number,
  blockedRoadIds: Set<string>,
  scenarioId: string = "historical_sept_2025"
): Promise<RoadGeoJSON> {
  const cacheKey = `${scenarioId}_${timestepIndex}`;
  try {
    const res = await fetch(
      `${API_BASE}/flood-state?scenario_id=${scenarioId}&slider_step=${timestepIndex}&slider_max=18`
    );
    if (!res.ok) throw new Error(`API returned ${res.status}`);
    const data: RoadGeoJSON = await res.json();
    if (blockedRoadIds && blockedRoadIds.size > 0) {
      data.features.forEach((f) => {
        if (blockedRoadIds.has(f.properties.id)) {
          f.properties.blocked = true;
        }
      });
    }
    cachedData[cacheKey] = data;
    return data;
  } catch (err) {
    console.warn("Backend offline or unreachable, falling back to local model:", err);
    return getMockRoadFloodData(timestepIndex, blockedRoadIds);
  }
}

export function getMockRoadFloodData(
  timestepIndex: number,
  blockedRoadIds: Set<string>
): RoadGeoJSON {
  if (cachedData[timestepIndex]) {
    const data = cachedData[timestepIndex];
    if (blockedRoadIds && blockedRoadIds.size > 0) {
      data.features.forEach((f) => {
        f.properties.blocked = blockedRoadIds.has(f.properties.id);
      });
    }
    return data;
  }

  const factor = Math.sin((timestepIndex / 18) * Math.PI);
  const nodeById = Object.fromEntries(ROAD_NODES.map((n) => [n.id, n]));

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

const cachedManholeData: Record<string, ManholeGeoJSON> = {};

export async function fetchRealManholesData(
  timestepIndex: number,
  scenarioId: string = "historical_sept_2025"
): Promise<ManholeGeoJSON> {
  const cacheKey = `${scenarioId}_${timestepIndex}`;
  if (cachedManholeData[cacheKey]) {
    return cachedManholeData[cacheKey];
  }
  try {
    const res = await fetch(
      `${API_BASE}/manholes?scenario_id=${scenarioId}&slider_step=${timestepIndex}&slider_max=18`
    );
    if (!res.ok) throw new Error(`API returned ${res.status}`);
    const data: ManholeGeoJSON = await res.json();
    cachedManholeData[cacheKey] = data;
    return data;
  } catch (err) {
    console.warn("Backend offline or unreachable, generating fallback manholes:", err);
    return getMockManholesData(timestepIndex);
  }
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