import { ShieldCheck, Zap } from "lucide-react";
import type { PriorityMode } from "../types/flood";

interface HeaderProps {
  priority: PriorityMode;
  setPriority: (p: PriorityMode) => void;
}

export default function Header({ priority, setPriority }: HeaderProps) {
  return (
    <header className="absolute top-4 left-4 z-10 bg-neutral-900/90 backdrop-blur-md border border-neutral-800 rounded-xl px-5 py-3 shadow-2xl flex items-center gap-4">
      <div>
        <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse" />
          Urban Flood Nowcast
        </h1>
        <p className="text-xs text-neutral-400">0–3h Street-Level Hydraulic Simulation</p>
      </div>

      <div className="flex bg-neutral-950 p-1 rounded-lg border border-neutral-800 text-xs">
        <button
          onClick={() => setPriority("safety")}
          className={`px-3 py-1 rounded-md flex items-center gap-1.5 ${
            priority === "safety" ? "bg-emerald-600 text-white font-medium" : "text-neutral-400 hover:text-neutral-200"
          }`}
        >
          <ShieldCheck className="w-3.5 h-3.5" /> Citizen Mode
        </button>
        <button
          onClick={() => setPriority("speed")}
          className={`px-3 py-1 rounded-md flex items-center gap-1.5 ${
            priority === "speed" ? "bg-amber-600 text-white font-medium" : "text-neutral-400 hover:text-neutral-200"
          }`}
        >
          <Zap className="w-3.5 h-3.5" /> Rescue Priority
        </button>
      </div>
    </header>
  );
} 