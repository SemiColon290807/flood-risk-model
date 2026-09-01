import type { RouteMode } from "../types/flood";

export const LANDMARK_PRESETS = [
  { name: "🎓 Jadavpur University Main Campus", nodeId: "N7262" },
  { name: "🚌 8B Bus Stand Terminus", nodeId: "N4086" },
  { name: "🏥 KPC Medical College & Hospital", nodeId: "N4613" },
  { name: "🚆 Dhakuria Lake / Station", nodeId: "N1367" },
  { name: "🏙️ Jodhpur Park Main Road", nodeId: "N1749" },
  { name: "🏫 Bikramgarh High School", nodeId: "N3742" },
  { name: "🌊 Santoshpur Lake Hub", nodeId: "N6362" },
  { name: "🚑 Bagha Jatin Hospital", nodeId: "N5220" },
  { name: "🏨 Ruby Hospital (EM Bypass)", nodeId: "N5116" },
];

interface RouteOverlayProps {
  start: string | null;
  setStart: (id: string) => void;
  end: string | null;
  setEnd: (id: string) => void;
  mode: RouteMode;
  setMode: (mode: RouteMode) => void;
  isPickingRoute: boolean;
  setIsPickingRoute: (fn: (prev: boolean) => boolean) => void;
  onClearRoute: () => void;
  onFindRoute: (start: string, end: string, mode: RouteMode) => void;
  routeFound: boolean | null;
}

export default function RouteOverlay({
  start,
  setStart,
  end,
  setEnd,
  mode,
  setMode,
  isPickingRoute,
  setIsPickingRoute,
  onClearRoute,
  onFindRoute,
  routeFound,
}: RouteOverlayProps) {
  const getLandmarkName = (id: string | null) => {
    if (!id) return "None selected";
    const found = LANDMARK_PRESETS.find((p) => p.nodeId === id);
    return found ? found.name : `Node ${id}`;
  };

  return (
    <div className="absolute top-24 left-6 z-20 w-80 rounded-xl bg-neutral-900/95 border border-neutral-800 p-4 text-neutral-100 shadow-2xl backdrop-blur-md">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-bold flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          Safe Evacuation Router
        </div>
        {(start || end || routeFound !== null) && (
          <button
            onClick={onClearRoute}
            className="text-[11px] text-neutral-400 hover:text-red-400 transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {/* Interactive Map Picking Banner */}
      <button
        onClick={() => setIsPickingRoute((prev) => !prev)}
        className={`w-full mb-3 p-2.5 rounded-lg border text-xs font-semibold flex items-center justify-between transition-all ${
          isPickingRoute
            ? "bg-blue-950/70 border-blue-500 text-blue-300 shadow-md shadow-blue-950"
            : "bg-neutral-950 hover:bg-neutral-800 border-neutral-800 text-neutral-300"
        }`}
      >
        <span className="flex items-center gap-1.5">
          <span>📍</span>
          <span>{isPickingRoute ? "Clicking Map to Select" : "Click on Map to Select"}</span>
        </span>
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full ${
            isPickingRoute ? "bg-blue-600 text-white" : "bg-neutral-800 text-neutral-400"
          }`}
        >
          {isPickingRoute ? "Active" : "Enable"}
        </span>
      </button>

      {isPickingRoute && (
        <div className="mb-3 p-2 rounded-lg bg-blue-950/40 border border-blue-900/40 text-[11px] text-blue-200 flex items-start gap-1.5">
          <span className="text-blue-400 font-bold">ℹ</span>
          <span>
            {!start
              ? "1. Click anywhere on the map to set Start (Pin A)."
              : !end
              ? "2. Click another location on the map to set Destination (Pin B)."
              : "Pins placed! Route auto-computed. Click map again to re-place."}
          </span>
        </div>
      )}

      {/* Start Selection */}
      <div className="mb-2.5">
        <div className="flex items-center justify-between mb-1">
          <label className="text-[11px] text-neutral-400 flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500" /> Start (Pin A)
          </label>
          <span className="text-[10px] text-neutral-500">{start ? `ID: ${start}` : "Unset"}</span>
        </div>
        <select
          value={start ?? ""}
          onChange={(e) => setStart(e.target.value)}
          className="w-full rounded-lg bg-neutral-950 border border-neutral-800 text-xs p-2 text-neutral-200"
        >
          <option value="" disabled>Select Landmark or Click Map</option>
          {start && !LANDMARK_PRESETS.some((p) => p.nodeId === start) && (
            <option value={start}>📍 Map Clicked Point ({start})</option>
          )}
          {LANDMARK_PRESETS.map((p) => (
            <option key={`start-${p.nodeId}`} value={p.nodeId}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      {/* Destination Selection */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1">
          <label className="text-[11px] text-neutral-400 flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-red-500" /> Destination (Pin B)
          </label>
          <span className="text-[10px] text-neutral-500">{end ? `ID: ${end}` : "Unset"}</span>
        </div>
        <select
          value={end ?? ""}
          onChange={(e) => setEnd(e.target.value)}
          className="w-full rounded-lg bg-neutral-950 border border-neutral-800 text-xs p-2 text-neutral-200"
        >
          <option value="" disabled>Select Landmark or Click Map</option>
          {end && !LANDMARK_PRESETS.some((p) => p.nodeId === end) && (
            <option value={end}>📍 Map Clicked Point ({end})</option>
          )}
          {LANDMARK_PRESETS.map((p) => (
            <option key={`end-${p.nodeId}`} value={p.nodeId}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      {/* Mode Switcher */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <button
          onClick={() => setMode("vehicle")}
          className={`text-xs py-1.5 px-2 rounded-lg border font-medium flex flex-col items-center gap-0.5 transition-all ${
            mode === "vehicle"
              ? "bg-amber-950/60 border-amber-500 text-amber-300"
              : "bg-neutral-950 border-neutral-800 text-neutral-400 hover:text-neutral-200"
          }`}
        >
          <span>🚗 Vehicle Mode</span>
          <span className="text-[10px] opacity-75">Max 30cm depth</span>
        </button>
        <button
          onClick={() => setMode("pedestrian")}
          className={`text-xs py-1.5 px-2 rounded-lg border font-medium flex flex-col items-center gap-0.5 transition-all ${
            mode === "pedestrian"
              ? "bg-emerald-950/60 border-emerald-500 text-emerald-300"
              : "bg-neutral-950 border-neutral-800 text-neutral-400 hover:text-neutral-200"
          }`}
        >
          <span>🚶 Pedestrian</span>
          <span className="text-[10px] opacity-75">Min wetted depth</span>
        </button>
      </div>

      {/* Find Route Button */}
      <button
        onClick={() => {
          if (start && end) onFindRoute(start, end, mode);
        }}
        disabled={!start || !end}
        className={`w-full text-xs font-semibold py-2 rounded-lg text-white shadow-lg transition-all flex items-center justify-center gap-1.5 ${
          start && end
            ? "bg-blue-600 hover:bg-blue-500 shadow-blue-900/30 cursor-pointer"
            : "bg-neutral-800 text-neutral-500 cursor-not-allowed"
        }`}
      >
        <span>Compute Safe Route</span>
      </button>

      {/* Status Messages */}
      {routeFound === false && (
        <div className="mt-2.5 p-2 rounded-lg bg-red-950/50 border border-red-900/60 text-red-300 text-xs flex items-start gap-1.5">
          <span className="text-red-400 font-bold">✕</span>
          <span>No safe route available — connecting roads exceed physical depth limit ({mode === "vehicle" ? "30cm" : "75cm"}) or are blocked.</span>
        </div>
      )}
      {routeFound === true && (
        <div className="mt-2.5 p-2 rounded-lg bg-emerald-950/50 border border-emerald-900/60 text-emerald-300 text-xs flex items-center gap-1.5">
          <span className="text-emerald-400 font-bold">✓</span>
          <span>Safe path found — highlighted in cyan on map.</span>
        </div>
      )}
    </div>
  );
}