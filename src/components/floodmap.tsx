import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { RoadSegmentProperties } from "../types/flood";
import { getMockRoadFloodData } from "../utils/mockdata";
import { FLOOD_COLORS } from "../utils/waterDepthLabel";

interface FloodMapProps {
  timestep: number;
  blockedRoadIds: Set<string>;
  routeEdgeIds: string[];
  onRoadClick: (road: RoadSegmentProperties) => void;
}

export default function FloodMap({
  timestep,
  blockedRoadIds,
  routeEdgeIds,
  onRoadClick,
}: FloodMapProps) {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapInstance = useRef<maplibregl.Map | null>(null);
  const isLoadedRef = useRef<boolean>(false);

  // Initialize Map
  useEffect(() => {
    if (!mapContainer.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
      center: [88.3715, 22.4988],
      zoom: 14,
      pitch: 30,
    });

    map.on("load", () => {
      isLoadedRef.current = true;

      // 1. Base Road Network Source
      map.addSource("roads", {
        type: "geojson",
        data: getMockRoadFloodData(timestep, blockedRoadIds),
      });

      // Regular Flood Risk Layer
      map.addLayer({
        id: "roads-layer",
        type: "line",
        source: "roads",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": 6,
          "line-color": [
            "match",
            ["get", "flooding_type"],
            "safe", FLOOD_COLORS.safe,
            "caution", FLOOD_COLORS.caution,
            "moderate", FLOOD_COLORS.moderate,
            "severe", FLOOD_COLORS.severe,
            "#999999",
          ],
          "line-opacity": 0.9,
        },
      });

      // Blocked Overlay Layer (Dashed Dark Line)
      map.addLayer({
        id: "roads-blocked-layer",
        type: "line",
        source: "roads",
        filter: ["==", ["get", "blocked"], true],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": 6,
          "line-color": "#09090b",
          "line-dasharray": [1, 1.5],
        },
      });

      // 2. Active Route Highlight Source & Layer
      const initialRoadData = getMockRoadFloodData(timestep, blockedRoadIds);
      const initialRouteFeatures = initialRoadData.features.filter((f) =>
        routeEdgeIds.includes(f.properties.id)
      );

      map.addSource("route", {
        type: "geojson",
        data: { type: "FeatureCollection", features: initialRouteFeatures },
      });

      // Route Glow Outline
      map.addLayer({
        id: "route-glow",
        type: "line",
        source: "route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": 10,
          "line-color": "#38bdf8",
          "line-opacity": 0.4,
          "line-blur": 3,
        },
      });

      // Route Core Line
      map.addLayer({
        id: "route-layer",
        type: "line",
        source: "route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": 5,
          "line-color": "#60a5fa",
          "line-opacity": 1,
        },
      });

      // Interactivity
      map.on("click", "roads-layer", (e) => {
        if (!e.features || e.features.length === 0) return;
        onRoadClick(e.features[0].properties as RoadSegmentProperties);
      });

      map.on("mouseenter", "roads-layer", () => {
        map.getCanvas().style.cursor = "pointer";
      });

      map.on("mouseleave", "roads-layer", () => {
        map.getCanvas().style.cursor = "";
      });
    });

    mapInstance.current = map;
    return () => {
      isLoadedRef.current = false;
      map.remove();
    };
  }, []);

  // Update Road Network GeoJSON on Time / Blockage change
  useEffect(() => {
    if (!mapInstance.current || !isLoadedRef.current) return;
    const source = mapInstance.current.getSource("roads") as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData(getMockRoadFloodData(timestep, blockedRoadIds));
    }
  }, [timestep, blockedRoadIds]);

  // Update Route GeoJSON on Route / Time change
  useEffect(() => {
    if (!mapInstance.current || !isLoadedRef.current) return;
    const routeSource = mapInstance.current.getSource("route") as maplibregl.GeoJSONSource | undefined;
    if (routeSource) {
      const roadData = getMockRoadFloodData(timestep, blockedRoadIds);
      const routeFeatures = roadData.features.filter((f) =>
        routeEdgeIds.includes(f.properties.id)
      );
      routeSource.setData({
        type: "FeatureCollection",
        features: routeFeatures,
      });
    }
  }, [routeEdgeIds, timestep, blockedRoadIds]);

  return <div ref={mapContainer} className="absolute inset-0 w-full h-full" />;
}