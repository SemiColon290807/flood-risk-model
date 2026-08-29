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

  useEffect(() => {
    if (!mapContainer.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
      center: [88.371, 22.498],
      zoom: 15,
    });

    map.on("load", () => {
      map.addSource("roads", {
        type: "geojson",
        data: getMockRoadFloodData(0, new Set()),
      });

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

      map.addLayer({
        id: "roads-blocked-layer",
        type: "line",
        source: "roads",
        filter: ["==", ["get", "blocked"], true],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": 6,
          "line-color": "#111111",
          "line-dasharray": [1, 1.5],
        },
      });

      map.addSource("route", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "route-layer",
        type: "line",
        source: "route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": 5,
          "line-color": "#3b82f6",
          "line-opacity": 0.95,
        },
      });

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
    (window as any).debugMap = map;
    return () => map.remove();
  }, []);

  useEffect(() => {
    if (!mapInstance.current || !mapInstance.current.isStyleLoaded()) return;
    const source = mapInstance.current.getSource("roads") as maplibregl.GeoJSONSource;
    source?.setData(getMockRoadFloodData(timestep, blockedRoadIds));
  }, [timestep, blockedRoadIds]);

  useEffect(() => {
    if (!mapInstance.current || !mapInstance.current.isStyleLoaded()) return;
    const roadData = getMockRoadFloodData(timestep, blockedRoadIds);
    const routeFeatures = roadData.features.filter((f) =>
      routeEdgeIds.includes(f.properties.id)
    );
    const routeSource = mapInstance.current.getSource("route") as maplibregl.GeoJSONSource;
    routeSource?.setData({ type: "FeatureCollection", features: routeFeatures });
  }, [routeEdgeIds, timestep, blockedRoadIds]);

  return <div ref={mapContainer} className="absolute inset-0 w-full h-full" />;
}