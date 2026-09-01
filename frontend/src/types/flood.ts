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
  path?: [number, number][];
}

export interface ScenarioInfo {
  id: string;
  name: string;
  category?: string;
  description?: string;
  timesteps: number;
  duration_hours: number;
  peak_intensity_mm_hr: number;
}

export interface ManholeProperties {
  id: string;
  node_idx: number;
  depth_cm: number;
  flooding_type: FloodingType;
  surcharge_status: string;
  stored_vol_m3: number;
  elevation_m: number;
  building_pct: number;
  effective_area_m2: number;
  connected_pipes: number;
}

export interface ManholeGeoJSON {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: {
      type: "Point";
      coordinates: [number, number];
    };
    properties: ManholeProperties;
  }[];
}