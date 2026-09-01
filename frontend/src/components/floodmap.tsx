import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { RoadSegmentProperties } from "../types/flood";
import { fetchRealRoadFloodData, getMockRoadFloodData } from "../utils/mockdata";
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
      zoom: 14.0,
      minZoom: 13.0,
      maxZoom: 18.0,
      maxBounds: [
        [88.320, 22.440], // Southwest boundary
        [88.425, 22.560], // Northeast boundary
      ],
      pitch: 20,
    });

    map.on("load", async () => {
      isLoadedRef.current = true;

      // 1. Base Road Network Source
      const initialRoadData = await fetchRealRoadFloodData(timestep, blockedRoadIds);

      map.addSource("roads", {
        type: "geojson",
        data: initialRoadData,
      });

      // Subtle Dark Casing Underlay to keep road edges crisp
      map.addLayer({
        id: "roads-casing",
        type: "line",
        source: "roads",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            13, 2.0,
            14, 3.2,
            16, 5.0,
            18, 7.5,
          ],
          "line-color": "#09090b",
          "line-opacity": 0.4,
        },
      });

      // Regular Flood Risk Layer (Dynamic Line-Width & Severity Opacity)
      map.addLayer({
        id: "roads-layer",
        type: "line",
        source: "roads",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            13, 1.4,
            14, 2.2,
            16, 3.8,
            18, 6.0,
          ],
          "line-color": [
            "match",
            ["get", "flooding_type"],
            "safe", FLOOD_COLORS.safe,
            "caution", FLOOD_COLORS.caution,
            "moderate", FLOOD_COLORS.moderate,
            "severe", FLOOD_COLORS.severe,
            "#999999",
          ],
          "line-opacity": [
            "match",
            ["get", "flooding_type"],
            "safe", 0.72,      // 80% of original opacity for safe streets
            "caution", 0.90,   // High visibility for caution
            "moderate", 0.95,  // Prominent for moderate
            "severe", 1.0,     // Full brightness for severe flood hazards
            0.72,
          ],
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
          "line-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            13, 1.8,
            14, 2.8,
            16, 4.5,
            18, 7.0,
          ],
          "line-color": "#09090b",
          "line-dasharray": [1, 1.5],
        },
      });

      // 2. Active Route Highlight Source & Layer
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

  // Update Road Network & Route GeoJSON on Time / Blockage change
  useEffect(() => {
    if (!mapInstance.current || !isLoadedRef.current) return;
    let isCancelled = false;

    fetchRealRoadFloodData(timestep, blockedRoadIds).then((roadData) => {
      if (isCancelled || !mapInstance.current) return;

      const source = mapInstance.current.getSource("roads") as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(roadData);
      }

      const routeSource = mapInstance.current.getSource("route") as maplibregl.GeoJSONSource | undefined;
      if (routeSource) {
        const routeFeatures = roadData.features.filter((f) =>
          routeEdgeIds.includes(f.properties.id)
        );
        routeSource.setData({
          type: "FeatureCollection",
          features: routeFeatures,
        });
      }
    });

    return () => {
      isCancelled = true;
    };
  }, [timestep, blockedRoadIds, routeEdgeIds]);

  return <div ref={mapContainer} className="absolute inset-0 w-full h-full" />;
}