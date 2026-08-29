export type PriorityMode = "safety" | "speed";
export type RouteMode = "pedestrian" | "vehicle";
export type FloodingType = "safe" | "caution" | "moderate" | "severe";

export interface RoadSegmentProperties {
  id: string;
  from: string;
  to: string;
  depth_cm: number;
  flooding_type: FloodingType;
  blocked: boolean;
  rainfall_mm: number;
  inflow_rate: number;
  pipe_capacity: number;
}

export interface RoadGeoJSON {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: {
      type: "LineString";
      coordinates: [number, number][];
    };
    properties: RoadSegmentProperties;
  }[];
}

export interface RoadNode {
  id: string;
  lng: number;
  lat: number;
}

export interface RoadEdge {
  id: string;
  from: string;
  to: string;
}