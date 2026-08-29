import { useState } from "react";
import { ROAD_NODES } from "../data/roadNetwork";
import type { RouteMode } from "../types/flood";

interface RouteOverlayProps {
  onFindRoute: (start: string, end: string, mode: RouteMode) => void;
  routeFound: boolean | null;
}

export default function RouteOverlay({ onFindRoute, routeFound }: RouteOverlayProps) {
  const [start, setStart] = useState(ROAD_NODES[0].id);
  const [end, setEnd] = useState(ROAD_NODES[ROAD_NODES.length - 1].id);
  const [mode, setMode] = useState<RouteMode>("pedestrian");

  return (
    <div className="absolute top-24 left-6 z-20 w-64 rounded-xl bg-neutral-900 border border-neutral-800 p-4 text-neutral-100 shadow-xl">
      <div className="text-sm font-bold mb-3">Safe Route Finder</div>

      <label className="text-xs text-neutral-400">Start</label>
      <select
        value={start}
        onChange={(e) => setStart(e.target.value)}
        className="w-full mb-2 rounded-md bg-neutral-950 border border-neutral-800 text-sm p-1.5"
      >
        {ROAD_NODES.map((n) => (
          <option key={n.id} value={n.id}>{n.id}</option>
        ))}
      </select>

      <label className="text-xs text-neutral-400">Destination</label>
      <select
        value={end}
        onChange={(e) => setEnd(e.target.value)}
        className="w-full mb-3 rounded-md bg-neutral-950 border border-neutral-800 text-sm p-1.5"
      >
        {ROAD_NODES.map((n) => (
          <option key={n.id} value={n.id}>{n.id}</option>
        ))}
      </select>

      <div className="flex gap-2 mb-3">
        <button
          onClick={() => setMode("pedestrian")}
          className={`flex-1 text-xs py-1.5 rounded-md border ${
            mode === "pedestrian"
              ? "bg-emerald-600 border-emerald-500"
              : "bg-neutral-950 border-neutral-800 text-neutral-400"
          }`}
        >
          Pedestrian
        </button>
        <button
          onClick={() => setMode("vehicle")}
          className={`flex-1 text-xs py-1.5 rounded-md border ${
            mode === "vehicle"
              ? "bg-amber-600 border-amber-500"
              : "bg-neutral-950 border-neutral-800 text-neutral-400"
          }`}
        >
          Vehicle
        </button>
      </div>

      <button
        onClick={() => onFindRoute(start, end, mode)}
        className="w-full text-sm font-semibold py-1.5 rounded-md bg-blue-600 hover:bg-blue-500"
      >
        Find Safe Route
      </button>

      {routeFound === false && (
        <div className="mt-2 text-xs text-red-400">
          No safe route available — every path is blocked or too deep.
        </div>
      )}
      {routeFound === true && (
        <div className="mt-2 text-xs text-emerald-400">
          Route found — shown in blue on the map.
        </div>
      )}
    </div>
  );
}