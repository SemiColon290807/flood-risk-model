import { ROAD_NODES, ROAD_EDGES } from "../data/roadNetwork";
import type { RoadGeoJSON, RouteMode } from "../types/flood";

interface GraphEdge {
  id: string;
  to: string;
  weight: number;
}

export function findSafeRoute(
  roadData: RoadGeoJSON,
  startNodeId: string,
  endNodeId: string,
  mode: RouteMode
): { path: string[]; usedEdgeIds: string[] } | null {
  const infoByEdge: Record<string, { depth: number; blocked: boolean }> = {};
  roadData.features.forEach((f) => {
    infoByEdge[f.properties.id] = {
      depth: f.properties.depth_cm,
      blocked: f.properties.blocked,
    };
  });

  const graph: Record<string, GraphEdge[]> = {};
  ROAD_NODES.forEach((n) => (graph[n.id] = []));

  ROAD_EDGES.forEach((edge) => {
    const info = infoByEdge[edge.id];
    if (!info || info.blocked) return;
    if (mode === "vehicle" && info.depth > 30) return;
    const weight = info.depth + 1;
    graph[edge.from].push({ id: edge.id, to: edge.to, weight });
    graph[edge.to].push({ id: edge.id, to: edge.from, weight });
  });

  const dist: Record<string, number> = {};
  const prevNode: Record<string, string | null> = {};
  const prevEdge: Record<string, string | null> = {};
  const visited = new Set<string>();

  ROAD_NODES.forEach((n) => {
    dist[n.id] = Infinity;
    prevNode[n.id] = null;
    prevEdge[n.id] = null;
  });
  dist[startNodeId] = 0;

  while (visited.size < ROAD_NODES.length) {
    let current: string | null = null;
    let currentDist = Infinity;
    for (const node of ROAD_NODES) {
      if (!visited.has(node.id) && dist[node.id] < currentDist) {
        current = node.id;
        currentDist = dist[node.id];
      }
    }
    if (current === null) break;
    visited.add(current);

    for (const edge of graph[current]) {
      const newDist = dist[current] + edge.weight;
      if (newDist < dist[edge.to]) {
        dist[edge.to] = newDist;
        prevNode[edge.to] = current;
        prevEdge[edge.to] = edge.id;
      }
    }
  }

  if (dist[endNodeId] === Infinity) return null;

  const path: string[] = [];
  const usedEdgeIds: string[] = [];
  let curr: string | null = endNodeId;
  while (curr !== null) {
    path.unshift(curr);
    const e = prevEdge[curr];
    if (e) usedEdgeIds.unshift(e);
    curr = prevNode[curr];
  }

  return { path, usedEdgeIds };
}