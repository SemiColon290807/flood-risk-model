import { ROAD_NODES, ROAD_EDGES } from "../data/roadNetwork";
import { getFloodingType } from "./waterDepthLabel";
import type { RoadGeoJSON } from "../types/flood";

const API_BASE = "http://localhost:8000";
const cachedData: Record<number, RoadGeoJSON> = {};

export async function fetchRealRoadFloodData(
  timestepIndex: number,
  blockedRoadIds: Set<string>
): Promise<RoadGeoJSON> {
  try {
    const res = await fetch(
      `${API_BASE}/flood-state?scenario_id=historical_sept_2025&slider_step=${timestepIndex}&slider_max=18`
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
    cachedData[timestepIndex] = data;
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