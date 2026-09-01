import { ShieldCheck, Zap, CircleDot } from "lucide-react";
import type { PriorityMode } from "../types/flood";

interface HeaderProps {
  priority: PriorityMode;
  setPriority: (p: PriorityMode) => void;
  showManholes: boolean;
  onToggleManholes: () => void;
}

export default function Header({
  priority,
  setPriority,
  showManholes,
  onToggleManholes,
}: HeaderProps) {
  return (
    <header className="absolute top-4 left-4 z-10 bg-neutral-900/90 backdrop-blur-md border border-neutral-800 rounded-xl px-4 py-2.5 shadow-2xl flex items-center gap-3.5">
      <div>
        <h1 className="text-sm font-bold tracking-tight text-white flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse" />
          Urban Flood Nowcast
        </h1>
        <p className="text-[11px] text-neutral-400">0–3h Street & Manhole Hydraulic Simulation</p>
      </div>

      <div className="flex bg-neutral-950 p-1 rounded-lg border border-neutral-800 text-xs">
        <button
          id="btn-citizen-mode"
          onClick={() => setPriority("safety")}
          className={`px-2.5 py-1 rounded-md flex items-center gap-1.5 transition-colors ${
            priority === "safety" ? "bg-emerald-600 text-white font-medium shadow-sm" : "text-neutral-400 hover:text-neutral-200"
          }`}
        >
          <ShieldCheck className="w-3.5 h-3.5" /> Citizen Mode
        </button>
        <button
          id="btn-rescue-mode"
          onClick={() => setPriority("speed")}
          className={`px-2.5 py-1 rounded-md flex items-center gap-1.5 transition-colors ${
            priority === "speed" ? "bg-amber-600 text-white font-medium shadow-sm" : "text-neutral-400 hover:text-neutral-200"
          }`}
        >
          <Zap className="w-3.5 h-3.5" /> Rescue Priority
        </button>
      </div>

      {/* Manholes Node Toggle Switch */}
      <button
        id="btn-toggle-manholes"
        onClick={onToggleManholes}
        className={`px-3 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition-all ${
          showManholes
            ? "bg-blue-600 border-blue-400 text-white shadow-lg shadow-blue-900/50 scale-105"
            : "bg-neutral-950 border-neutral-800 text-neutral-300 hover:text-white hover:bg-neutral-800"
        }`}
        title="Toggle display of 8,001 drainage manhole nodes"
      >
        <CircleDot className={`w-3.5 h-3.5 ${showManholes ? "text-white animate-pulse" : "text-neutral-400"}`} />
        <span>Manholes ({showManholes ? "ON" : "OFF"})</span>
      </button>
    </header>
  );
} 