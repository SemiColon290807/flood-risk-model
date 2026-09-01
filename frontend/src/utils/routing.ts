import { ROAD_NODES, ROAD_EDGES } from "../data/roadNetwork";
import type { RoadNode, RoadGeoJSON, RouteMode } from "../types/flood";

export function findNearestNode(lng: number, lat: number): RoadNode {
  let best = ROAD_NODES[0];
  let bestDist = Infinity;
  for (const n of ROAD_NODES) {
    const d = (n.lng - lng) ** 2 + (n.lat - lat) ** 2;
    if (d < bestDist) {
      bestDist = d;
      best = n;
    }
  }
  return best;
}

function pathLength(coords: [number, number][]): number {
  let total = 0;
  for (let i = 0; i < coords.length - 1; i++) {
    const [lng1, lat1] = coords[i];
    const [lng2, lat2] = coords[i + 1];
    total += Math.sqrt((lng2 - lng1) ** 2 + (lat2 - lat1) ** 2);
  }
  return total;
}

interface GraphEdge {
  id: string;
  to: string;
  weight: number;
}

class MinPriorityQueue {
  private heap: { node: string; dist: number }[] = [];

  push(node: string, dist: number) {
    this.heap.push({ node, dist });
    this._up(this.heap.length - 1);
  }

  pop(): { node: string; dist: number } | undefined {
    if (this.heap.length === 0) return undefined;
    const top = this.heap[0];
    const bottom = this.heap.pop()!;
    if (this.heap.length > 0) {
      this.heap[0] = bottom;
      this._down(0);
    }
    return top;
  }

  isEmpty(): boolean {
    return this.heap.length === 0;
  }

  private _up(i: number) {
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (this.heap[i].dist < this.heap[p].dist) {
        [this.heap[i], this.heap[p]] = [this.heap[p], this.heap[i]];
        i = p;
      } else break;
    }
  }

  private _down(i: number) {
    const len = this.heap.length;
    while (true) {
      let smallest = i;
      const left = (i << 1) + 1;
      const right = (i << 1) + 2;
      if (left < len && this.heap[left].dist < this.heap[smallest].dist) smallest = left;
      if (right < len && this.heap[right].dist < this.heap[smallest].dist) smallest = right;
      if (smallest !== i) {
        [this.heap[i], this.heap[smallest]] = [this.heap[smallest], this.heap[i]];
        i = smallest;
      } else break;
    }
  }
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

  const nodeById = Object.fromEntries(ROAD_NODES.map((n) => [n.id, n]));
  const graph: Record<string, GraphEdge[]> = {};
  ROAD_NODES.forEach((n) => (graph[n.id] = []));

  ROAD_EDGES.forEach((edge) => {
    const info = infoByEdge[edge.id];
    if (!info || info.blocked) return;
    if (mode === "vehicle" && info.depth > 30) return; // 30cm vehicle stall limit
    if (mode === "pedestrian" && info.depth > 75) return; // 75cm dangerous wading limit

    const fromNode = nodeById[edge.from];
    const toNode = nodeById[edge.to];
    if (!fromNode || !toNode) return;

    const fullPath: [number, number][] = [
      [fromNode.lng, fromNode.lat],
      ...(edge.path ?? []),
      [toNode.lng, toNode.lat],
    ];
    const distanceWeight = pathLength(fullPath) * 100000;
    const weight = distanceWeight + info.depth * 10;
    graph[edge.from].push({ id: edge.id, to: edge.to, weight });
    graph[edge.to].push({ id: edge.id, to: edge.from, weight });
  });

  const dist: Record<string, number> = {};
  const prevNode: Record<string, string | null> = {};
  const prevEdge: Record<string, string | null> = {};

  ROAD_NODES.forEach((n) => {
    dist[n.id] = Infinity;
    prevNode[n.id] = null;
    prevEdge[n.id] = null;
  });
  dist[startNodeId] = 0;

  const pq = new MinPriorityQueue();
  pq.push(startNodeId, 0);

  while (!pq.isEmpty()) {
    const top = pq.pop()!;
    const u = top.node;
    if (top.dist > dist[u]) continue;
    if (u === endNodeId) break;

    for (const edge of graph[u] || []) {
      const newDist = dist[u] + edge.weight;
      if (newDist < dist[edge.to]) {
        dist[edge.to] = newDist;
        prevNode[edge.to] = u;
        prevEdge[edge.to] = edge.id;
        pq.push(edge.to, newDist);
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