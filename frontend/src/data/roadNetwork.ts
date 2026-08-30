import type { RoadNode, RoadEdge } from "../types/flood";

export const BASE_LNG = 88.371;
export const BASE_LAT = 22.498;
const STEP = 0.003;

export const ROAD_NODES: RoadNode[] = [
  { id: "N1", lng: BASE_LNG + 0 * STEP, lat: BASE_LAT + 0 * STEP },
  { id: "N2", lng: BASE_LNG + 1 * STEP, lat: BASE_LAT + 0 * STEP },
  { id: "N3", lng: BASE_LNG + 2 * STEP, lat: BASE_LAT + 0 * STEP },
  { id: "N4", lng: BASE_LNG + 0 * STEP, lat: BASE_LAT - 1 * STEP },
  { id: "N5", lng: BASE_LNG + 1 * STEP, lat: BASE_LAT - 1 * STEP },
  { id: "N6", lng: BASE_LNG + 2 * STEP, lat: BASE_LAT - 1 * STEP },
  { id: "N7", lng: BASE_LNG + 0 * STEP, lat: BASE_LAT - 2 * STEP },
  { id: "N8", lng: BASE_LNG + 1 * STEP, lat: BASE_LAT - 2 * STEP },
  { id: "N9", lng: BASE_LNG + 2 * STEP, lat: BASE_LAT - 2 * STEP },
];

export const ROAD_EDGES: RoadEdge[] = [
  { id: "R1", from: "N1", to: "N2" },
  { id: "R2", from: "N2", to: "N3" },
  { id: "R3", from: "N4", to: "N5" },
  { id: "R4", from: "N5", to: "N6" },
  { id: "R5", from: "N7", to: "N8" },
  { id: "R6", from: "N8", to: "N9" },
  { id: "R7", from: "N1", to: "N4" },
  { id: "R8", from: "N4", to: "N7" },
  { id: "R9", from: "N2", to: "N5" },
  { id: "R10", from: "N5", to: "N8" },
  { id: "R11", from: "N3", to: "N6" },
  { id: "R12", from: "N6", to: "N9" },
];