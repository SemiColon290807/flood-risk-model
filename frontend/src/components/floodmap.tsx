import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { RoadSegmentProperties, ManholeProperties } from "../types/flood";
import { fetchRealRoadFloodData, fetchRealManholesData } from "../utils/mockdata";
import { FLOOD_COLORS } from "../utils/waterDepthLabel";
import { ROAD_NODES } from "../data/roadNetwork";

function buildPinsGeoJSON(startNodeId?: string | null, endNodeId?: string | null): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  if (startNodeId) {
    const nodeA = ROAD_NODES.find((n) => n.id === startNodeId);
    if (nodeA) {
      features.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: [nodeA.lng, nodeA.lat] },
        properties: { label: "A", type: "start", color: "#10b981", title: "Start Origin" },
      });
    }
  }
  if (endNodeId) {
    const nodeB = ROAD_NODES.find((n) => n.id === endNodeId);
    if (nodeB) {
      features.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: [nodeB.lng, nodeB.lat] },
        properties: { label: "B", type: "end", color: "#ef4444", title: "Destination" },
      });
    }
  }
  return { type: "FeatureCollection", features };
}

interface FloodMapProps {
  timestep: number;
  blockedRoadIds: Set<string>;
  routeEdgeIds: string[];
  scenarioId?: string;
  showManholes?: boolean;
  startNodeId?: string | null;
  endNodeId?: string | null;
  isPickingRoute?: boolean;
  onRoadClick: (road: RoadSegmentProperties) => void;
  onManholeClick?: (manhole: ManholeProperties) => void;
  onMapClickLocation?: (lng: number, lat: number) => void;
}

export default function FloodMap({
  timestep,
  blockedRoadIds,
  routeEdgeIds,
  scenarioId,
  showManholes = false,
  startNodeId,
  endNodeId,
  isPickingRoute,
  onRoadClick,
  onManholeClick,
  onMapClickLocation,
}: FloodMapProps) {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapInstance = useRef<maplibregl.Map | null>(null);
  const isLoadedRef = useRef<boolean>(false);

  // Latest callback refs to prevent stale closure bugs
  const onMapClickLocationRef = useRef(onMapClickLocation);
  onMapClickLocationRef.current = onMapClickLocation;

  const isPickingRouteRef = useRef(isPickingRoute);
  isPickingRouteRef.current = isPickingRoute;

  const onRoadClickRef = useRef(onRoadClick);
  onRoadClickRef.current = onRoadClick;

  const onManholeClickRef = useRef(onManholeClick);
  onManholeClickRef.current = onManholeClick;

  // Initialize Map
  useEffect(() => {
    if (!mapContainer.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
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
      const initialRoadData = await fetchRealRoadFloodData(timestep, blockedRoadIds, scenarioId);

      map.addSource("roads", {
        type: "geojson",
        data: initialRoadData,
      });

      // Subtle White Casing Underlay to keep road edges crisp on light map
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
            13, 2.2,
            14, 3.4,
            16, 5.2,
            18, 7.8,
          ],
          "line-color": "#ffffff",
          "line-opacity": 0.8,
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
            "safe", 0.72,
            "caution", 0.90,
            "moderate", 0.95,
            "severe", 1.0,
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
          "line-width": 12,
          "line-color": "#38bdf8",
          "line-opacity": 0.5,
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
          "line-color": "#0284c7",
          "line-opacity": 1,
        },
      });

      // 3. WebGL Native Pin Markers (Pins A & B)
      map.addSource("pins", {
        type: "geojson",
        data: buildPinsGeoJSON(startNodeId, endNodeId),
      });

      // Pin Radar Halo
      map.addLayer({
        id: "pins-halo",
        type: "circle",
        source: "pins",
        paint: {
          "circle-radius": 18,
          "circle-color": ["get", "color"],
          "circle-opacity": 0.35,
          "circle-blur": 0.4,
        },
      });

      // Pin Core Disc
      map.addLayer({
        id: "pins-core",
        type: "circle",
        source: "pins",
        paint: {
          "circle-radius": 10,
          "circle-color": ["get", "color"],
          "circle-stroke-width": 3,
          "circle-stroke-color": "#ffffff",
        },
      });

      // Pin Center Letter ("A" / "B")
      map.addLayer({
        id: "pins-text",
        type: "symbol",
        source: "pins",
        layout: {
          "text-field": ["get", "label"],
          "text-size": 11,
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: {
          "text-color": "#ffffff",
        },
      });

      // 4. Manholes Layer (8,001 Drainage Basins)
      const initialManholesData = await fetchRealManholesData(timestep, scenarioId);
      map.addSource("manholes", {
        type: "geojson",
        data: initialManholesData,
      });

      // Manhole Halo Glow
      map.addLayer({
        id: "manholes-halo",
        type: "circle",
        source: "manholes",
        layout: {
          visibility: showManholes ? "visible" : "none",
        },
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            13, 3.5,
            15, 6.0,
            18, 12.0,
          ],
          "circle-color": [
            "match",
            ["get", "flooding_type"],
            "safe", "#10b981",
            "caution", "#facc15",
            "moderate", "#f97316",
            "severe", "#ef4444",
            "#38bdf8",
          ],
          "circle-opacity": 0.35,
          "circle-blur": 0.4,
        },
      });

      // Manhole Core Dot
      map.addLayer({
        id: "manholes-circle",
        type: "circle",
        source: "manholes",
        layout: {
          visibility: showManholes ? "visible" : "none",
        },
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            13, 2.5,
            15, 4.5,
            18, 7.5,
          ],
          "circle-color": [
            "match",
            ["get", "flooding_type"],
            "safe", "#10b981",
            "caution", "#facc15",
            "moderate", "#f97316",
            "severe", "#ef4444",
            "#38bdf8",
          ],
          "circle-stroke-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            13, 1.0,
            16, 1.8,
            18, 2.5,
          ],
          "circle-stroke-color": "#ffffff",
          "circle-opacity": 0.95,
        },
      });

      // Manhole Click
      map.on("click", "manholes-circle", (e) => {
        if (isPickingRouteRef.current) return;
        if (!e.features || e.features.length === 0) return;
        if (onManholeClickRef.current) {
          onManholeClickRef.current(e.features[0].properties as unknown as ManholeProperties);
        }
      });

      map.on("mouseenter", "manholes-circle", () => {
        if (!isPickingRouteRef.current) {
          map.getCanvas().style.cursor = "pointer";
        }
      });

      map.on("mouseleave", "manholes-circle", () => {
        if (!isPickingRouteRef.current) {
          map.getCanvas().style.cursor = "";
        }
      });

      // Global Map Click
      map.on("click", (e) => {
        if (isPickingRouteRef.current && onMapClickLocationRef.current) {
          onMapClickLocationRef.current(e.lngLat.lng, e.lngLat.lat);
        }
      });

      // Road Segment Click (for inspector panel)
      map.on("click", "roads-layer", (e) => {
        if (isPickingRouteRef.current) return;
        if (!e.features || e.features.length === 0) return;
        if (onRoadClickRef.current) {
          onRoadClickRef.current(e.features[0].properties as RoadSegmentProperties);
        }
      });

      map.on("mouseenter", "roads-layer", () => {
        if (!isPickingRouteRef.current) {
          map.getCanvas().style.cursor = "pointer";
        }
      });

      map.on("mouseleave", "roads-layer", () => {
        if (!isPickingRouteRef.current) {
          map.getCanvas().style.cursor = "";
        }
      });
    });

    mapInstance.current = map;
    return () => {
      isLoadedRef.current = false;
      map.remove();
    };
  }, []);

  // Update Cursor when Picking Mode changes
  useEffect(() => {
    if (!mapInstance.current) return;
    mapInstance.current.getCanvas().style.cursor = isPickingRoute ? "crosshair" : "";
  }, [isPickingRoute]);

  // Update Manholes Visibility when toggle changes
  useEffect(() => {
    if (!mapInstance.current || !isLoadedRef.current) return;
    const vis = showManholes ? "visible" : "none";
    if (mapInstance.current.getLayer("manholes-halo")) {
      mapInstance.current.setLayoutProperty("manholes-halo", "visibility", vis);
    }
    if (mapInstance.current.getLayer("manholes-circle")) {
      mapInstance.current.setLayoutProperty("manholes-circle", "visibility", vis);
    }
  }, [showManholes]);

  // Update Pins GeoJSON whenever startNodeId or endNodeId changes
  useEffect(() => {
    if (!mapInstance.current || !isLoadedRef.current) return;
    const pinSource = mapInstance.current.getSource("pins") as maplibregl.GeoJSONSource | undefined;
    if (pinSource) {
      pinSource.setData(buildPinsGeoJSON(startNodeId, endNodeId));
    }
  }, [startNodeId, endNodeId]);

  // Update Road Network & Manholes on Time / Blockage / Scenario change
  useEffect(() => {
    if (!mapInstance.current || !isLoadedRef.current) return;
    let isCancelled = false;

    fetchRealRoadFloodData(timestep, blockedRoadIds, scenarioId).then((roadData) => {
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

    if (showManholes) {
      fetchRealManholesData(timestep, scenarioId).then((mdata) => {
        if (isCancelled || !mapInstance.current) return;
        const msource = mapInstance.current.getSource("manholes") as maplibregl.GeoJSONSource | undefined;
        if (msource) {
          msource.setData(mdata);
        }
      });
    }

    return () => {
      isCancelled = true;
    };
  }, [timestep, blockedRoadIds, routeEdgeIds, scenarioId, showManholes]);

  return <div ref={mapContainer} className="absolute inset-0 w-full h-full" />;
}