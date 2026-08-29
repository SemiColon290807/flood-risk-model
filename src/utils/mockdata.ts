import { ROAD_NODES, ROAD_EDGES } from "../data/roadNetwork";
import { getFloodingType } from "./waterDepthLabel";
import type { RoadGeoJSON } from "../types/flood";

export function getMockRoadFloodData(
  timestepIndex: number,
  blockedRoadIds: Set<string>
): RoadGeoJSON {
  const factor = Math.sin((timestepIndex / 35) * Math.PI);
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