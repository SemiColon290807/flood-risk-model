import { FloodGeoJSON } from "../types/flood";

// Base center: e.g., Jadavpur University / Kolkata demo pocket [lng, lat]
const BASE_LNG = 88.371;
const BASE_LAT = 22.498;

export function getMockFloodData(timestepIndex: number): FloodGeoJSON {
  // 36 timesteps (0 to 180 min, 5 min intervals)
  // Severity peaks around timestep 18-24 (90-120 min)
  const factor = Math.sin((timestepIndex / 35) * Math.PI);

  const nodes = [
    { id: "NODE_01", offset: [0.002, 0.003], baseCap: 1.2 },
    { id: "NODE_02", offset: [-0.003, 0.001], baseCap: 0.8 },
    { id: "NODE_03", offset: [0.001, -0.004], baseCap: 1.5 },
    { id: "NODE_04", offset: [-0.002, -0.002], baseCap: 0.6 },
    { id: "NODE_05", offset: [0.004, 0.002], baseCap: 2.0 },
  ];

  return {
    type: "FeatureCollection",
    features: nodes.map((node) => {
      const inflow = +(node.baseCap * factor * 1.8).toFixed(2);
      const depth = Math.max(0, Math.round((inflow - node.baseCap) * 35)); // cm
      return {
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [BASE_LNG + node.offset[0], BASE_LAT + node.offset[1]],
        },
        properties: {
          id: node.id,
          depth_cm: depth,
          inflow_rate: inflow,
          pipe_capacity: node.baseCap,
          rainfall_mm: +(factor * 45).toFixed(1),
          blockage_percent: 0,
        },
      };
    }),
  };
}