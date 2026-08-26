import React, { useEffect, useRef, useState } from "react";
import maplibregl, { Map, GeoJSONSource } from "maplibre-gl";
import { Play, Pause, AlertTriangle, ShieldCheck, Zap, X } from "lucide-react";
import { FloodGeoJSON, FloodNodeProperties, PriorityMode } from "./types/flood";
import { getMockFloodData } from "./utils/mockData";

export default function App() {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapInstance = useRef<Map | null>(null);

  const [timestep, setTimestep] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [selectedNode, setSelectedNode] = useState<FloodNodeProperties | null>(null);
  const [priority, setPriority] = useState<PriorityMode>("safety");

  // Format timestep (5-min intervals: 0 to 35 = 0h to 3h)
  const formatTime = (step: number) => {
    const totalMinutes = step * 5;
    const hours = Math.floor(totalMinutes / 60);
    const mins = totalMinutes % 60;
    return `+${hours}h ${mins.toString().padStart(2, "0")}m`;
  };

  // Initialize MapLibre
  useEffect(() => {
    if (!mapContainer.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
      center: [88.371, 22.498],
      zoom: 15,
    });

    map.on("load", () => {
      const initialData = getMockFloodData(0);

      map.addSource("drainage-nodes", {
        type: "geojson",
        data: initialData,
      });

      // Data-driven WebGL circle styling: Green -> Yellow -> Orange -> Red
      map.addLayer({
        id: "drainage-nodes-layer",
        type: "circle",
        source: "drainage-nodes",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["get", "depth_cm"],
            0, 6,
            10, 10,
            30, 16,
            60, 24,
          ],
          "circle-color": [
            "step",
            ["get", "depth_cm"],
            "#22c55e", // 0 depth: safe (green)
            1, "#eab308", // 1-15 cm: caution (yellow)
            15, "#f97316", // 15-30 cm: moderate (orange)
            30, "#ef4444", // >30 cm: severe (red)
          ],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
          "circle-opacity": 0.85,
        },
      });

      // Click-to-inspect handler
      map.on("click", "drainage-nodes-layer", (e) => {
        if (!e.features || e.features.length === 0) return;
        const props = e.features[0].properties as FloodNodeProperties;
        setSelectedNode(props);
      });

      map.on("mouseenter", "drainage-nodes-layer", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "drainage-nodes-layer", () => {
        map.getCanvas().style.cursor = "";
      });
    });

    mapInstance.current = map;
    return () => map.remove();
  }, []);

  // Update map layer instantaneously when timestep changes
  useEffect(() => {
    if (!mapInstance.current || !mapInstance.current.isStyleLoaded()) return;
    const source = mapInstance.current.getSource("drainage-nodes") as GeoJSONSource;
    if (source) {
      source.setData(getMockFloodData(timestep));
    }
  }, [timestep]);

  // Autoplay loop for demo presentation
  useEffect(() => {
    let timer: number;
    if (isPlaying) {
      timer = window.setInterval(() => {
        setTimestep((prev) => (prev >= 35 ? 0 : prev + 1));
      }, 500);
    }
    return () => clearInterval(timer);
  }, [isPlaying]);

  return (
    <div className="relative w-screen h-screen bg-neutral-950 font-sans text-neutral-100 overflow-hidden">
      {/* 1. Map Canvas */}
      <div ref={mapContainer} className="absolute inset-0 w-full h-full" />

      {/* 2. Header Bar */}
      <header className="absolute top-4 left-4 z-10 bg-neutral-900/90 backdrop-blur-md border border-neutral-800 rounded-xl px-5 py-3 shadow-2xl flex items-center gap-4">
        <div>
          <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse" />
            Urban Flood Nowcast
          </h1>
          <p className="text-xs text-neutral-400">0–3h Street-Level Hydraulic Simulation</p>
        </div>

        {/* Priority Toggle */}
        <div className="flex bg-neutral-950 p-1 rounded-lg border border-neutral-800 text-xs">
          <button
            onClick={() => setPriority("safety")}
            className={`px-3 py-1 rounded-md transition-all flex items-center gap-1.5 ${
              priority === "safety" ? "bg-emerald-600 text-white font-medium" : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            <ShieldCheck className="w-3.5 h-3.5" /> Citizen Mode
          </button>
          <button
            onClick={() => setPriority("speed")}
            className={`px-3 py-1 rounded-md transition-all flex items-center gap-1.5 ${
              priority === "speed" ? "bg-amber-600 text-white font-medium" : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            <Zap className="w-3.5 h-3.5" /> Rescue Priority
          </button>
        </div>
      </header>

      {/* 3. Time Slider Controller (Core Demo Widget) */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-10 w-[90%] max-w-2xl bg-neutral-900/95 backdrop-blur-md border border-neutral-800 rounded-2xl p-4 shadow-2xl">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              className="p-2 bg-neutral-800 hover:bg-neutral-700 text-white rounded-lg transition"
            >
              {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
            </button>
            <span className="text-sm font-semibold tracking-wider text-emerald-400">
              {formatTime(timestep)}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-neutral-400">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Safe</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-yellow-500" /> Caution</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-orange-500" /> Moderate</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" /> Severe (&gt;30cm)</span>
          </div>
        </div>

        <input
          type="range"
          min="0"
          max="35"
          step="1"
          value={timestep}
          onChange={(e) => setTimestep(Number(e.target.value))}
          className="w-full accent-emerald-500 bg-neutral-800 h-2 rounded-lg cursor-pointer"
        />
        <div className="flex justify-between text-[10px] text-neutral-500 mt-1">
          <span>Now (t=0)</span>
          <span>+1.5 Hours</span>
          <span>+3.0 Hours</span>
        </div>
      </div>

      {/* 4. Click-to-Inspect Hydraulic Side Panel */}
      {selectedNode && (
        <aside className="absolute right-4 top-4 bottom-8 w-80 z-20 bg-neutral-900/95 backdrop-blur-md border border-neutral-800 rounded-2xl p-5 shadow-2xl flex flex-col justify-between animate-in slide-in-from-right">
          <div>
            <div className="flex items-center justify-between border-b border-neutral-800 pb-3">
              <div>
                <h2 className="text-sm font-bold text-white tracking-wide">{selectedNode.id}</h2>
                <p className="text-xs text-neutral-400">Drainage Inlet Node</p>
              </div>
              <button
                onClick={() => setSelectedNode(null)}
                className="p-1 text-neutral-400 hover:text-white rounded-md"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Severity Status Card */}
            <div className="mt-4 p-3.5 rounded-xl bg-neutral-950 border border-neutral-800">
              <div className="text-xs text-neutral-400 uppercase tracking-wider">Predicted Depth</div>
              <div className="text-3xl font-black text-white mt-1 flex items-baseline gap-1">
                {selectedNode.depth_cm} <span className="text-xs font-medium text-neutral-400">cm</span>
              </div>
            </div>

            {/* Hydraulic Math Breakdown */}
            <div className="mt-4 space-y-2.5 text-xs">
              <div className="flex justify-between py-1 border-b border-neutral-800/60">
                <span className="text-neutral-400">Inflow Rate</span>
                <span className="font-mono text-neutral-200">{selectedNode.inflow_rate} m³/s</span>
              </div>
              <div className="flex justify-between py-1 border-b border-neutral-800/60">
                <span className="text-neutral-400">Pipe Capacity</span>
                <span className="font-mono text-neutral-200">{selectedNode.pipe_capacity} m³/s</span>
              </div>
              <div className="flex justify-between py-1 border-b border-neutral-800/60">
                <span className="text-neutral-400">Rainfall Contribution</span>
                <span className="font-mono text-neutral-200">{selectedNode.rainfall_mm} mm/h</span>
              </div>
            </div>

            {selectedNode.inflow_rate > selectedNode.pipe_capacity && (
              <div className="mt-4 p-2.5 bg-red-950/40 border border-red-900/50 rounded-lg flex items-start gap-2 text-[11px] text-red-300">
                <AlertTriangle className="w-4 h-4 shrink-0 text-red-400" />
                <span>Pipe capacity exceeded by {+(selectedNode.inflow_rate - selectedNode.pipe_capacity).toFixed(2)} m³/s. Water backing up to surface.</span>
              </div>
            )}
          </div>

          <div className="text-[10px] text-neutral-500 text-center">
            Click anywhere on the map to dismiss
          </div>
        </aside>
      )}
    </div>
  );
}