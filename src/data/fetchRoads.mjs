import fs from "fs";

const BASE_LNG = 88.371;
const BASE_LAT = 22.498;
const RADIUS_METERS = 800;

const query = `[out:json][timeout:25];(way["highway"~"^(primary|secondary|tertiary|residential|unclassified|service)$"](around:${RADIUS_METERS},${BASE_LAT},${BASE_LNG}););out body;>;out skel qt;`;

const endpoints = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
];

async function fetchFromOverpass() {
  for (const url of endpoints) {
    console.log(`Trying ${url} ...`);
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "User-Agent": "flood-nowcast-hackathon-project/1.0",
        },
        body: "data=" + encodeURIComponent(query),
      });
      const text = await res.text();
      if (!res.ok) {
        console.log(`  Failed (status ${res.status}). Response snippet:`);
        console.log("  " + text.slice(0, 300));
        continue;
      }
      const data = JSON.parse(text);
      console.log(`  Success from ${url}`);
      return data;
    } catch (err) {
      console.log(`  Error: ${err.message}, trying next...`);
    }
  }
  throw new Error("All Overpass endpoints failed.");
}

const data = await fetchFromOverpass();

const nodesById = {};
data.elements.forEach((el) => {
  if (el.type === "node") nodesById[el.id] = { lng: el.lon, lat: el.lat };
});

const ROAD_NODES = [];
const ROAD_EDGES = [];
let nodeCounter = 1;
let edgeCounter = 1;
const nodeIdMap = {};

function getOrCreateNode(osmId) {
  if (nodeIdMap[osmId]) return nodeIdMap[osmId];
  const id = `N${nodeCounter++}`;
  nodeIdMap[osmId] = id;
  ROAD_NODES.push({ id, lng: nodesById[osmId].lng, lat: nodesById[osmId].lat });
  return id;
}

data.elements
  .filter((el) => el.type === "way")
  .forEach((way) => {
    const nodeIds = way.nodes;
    if (nodeIds.length < 2) return;
    const fromId = getOrCreateNode(nodeIds[0]);
    const toId = getOrCreateNode(nodeIds[nodeIds.length - 1]);
    const path = nodeIds
      .slice(1, -1)
      .map((n) => [nodesById[n].lng, nodesById[n].lat]);
    ROAD_EDGES.push({ id: `R${edgeCounter++}`, from: fromId, to: toId, path });
  });

if (ROAD_NODES.length === 0) {
  console.log("WARNING: No road data returned.");
  process.exit(1);
}

const output = `import type { RoadNode, RoadEdge } from "../types/flood";

export const BASE_LNG = ${BASE_LNG};
export const BASE_LAT = ${BASE_LAT};

export const ROAD_NODES: RoadNode[] = ${JSON.stringify(ROAD_NODES, null, 2)};

export const ROAD_EDGES: RoadEdge[] = ${JSON.stringify(ROAD_EDGES, null, 2)};
`;

fs.writeFileSync("src/data/roadNetwork.ts", output);
console.log(`Done. ${ROAD_NODES.length} nodes, ${ROAD_EDGES.length} edges written.`);