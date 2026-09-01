import { X, ArrowRight, CircleDot } from "lucide-react";
import type { ManholeProperties } from "../types/flood";

interface ManholePanelProps {
  manhole: ManholeProperties;
  onClose: () => void;
  onSetStart?: (nodeId: string) => void;
  onSetDestination?: (nodeId: string) => void;
}

export default function ManholePanel({
  manhole,
  onClose,
  onSetStart,
  onSetDestination,
}: ManholePanelProps) {
  const getStatusColor = (type: string) => {
    switch (type) {
      case "severe":
        return "bg-red-950/80 border-red-800 text-red-300";
      case "moderate":
        return "bg-amber-950/80 border-amber-800 text-amber-300";
      case "caution":
        return "bg-yellow-950/80 border-yellow-800 text-yellow-300";
      default:
        return "bg-emerald-950/80 border-emerald-800 text-emerald-300";
    }
  };

  return (
    <div className="absolute bottom-6 right-6 z-30 w-80 rounded-xl bg-neutral-900/95 border border-neutral-800 p-4 text-neutral-100 shadow-2xl backdrop-blur-md transition-all animate-in fade-in slide-in-from-bottom-2">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-neutral-800">
        <div className="flex items-center gap-2">
          <CircleDot className="w-4 h-4 text-blue-400" />
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
              <span>Manhole Junction</span>
              <span className="text-blue-400 font-mono">{manhole.id}</span>
            </h3>
            <span className="text-[10px] text-neutral-400">Index #{manhole.node_idx} (Drainage Inflow Basin)</span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-neutral-400 hover:text-white p-1 rounded-lg hover:bg-neutral-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Hydraulic Surcharge Status Badge */}
      <div className={`mt-3 p-2.5 rounded-lg border text-xs font-semibold flex items-center justify-between ${getStatusColor(manhole.flooding_type)}`}>
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${manhole.flooding_type === "severe" ? "bg-red-400 animate-ping" : manhole.flooding_type === "moderate" ? "bg-amber-400" : manhole.flooding_type === "caution" ? "bg-yellow-400" : "bg-emerald-400"}`} />
          <span>{manhole.surcharge_status}</span>
        </div>
        <span className="text-[11px] opacity-90">{manhole.depth_cm} cm</span>
      </div>

      {/* Grid of Engineering Metrics */}
      <div className="grid grid-cols-2 gap-2 mt-3 text-xs">
        <div className="p-2.5 rounded-lg bg-neutral-950/70 border border-neutral-800/80">
          <span className="text-[10px] text-neutral-400 block mb-0.5">Water Depth above Lid</span>
          <span className="text-sm font-bold text-neutral-100">{manhole.depth_cm} <span className="text-xs font-normal text-neutral-400">cm</span></span>
        </div>

        <div className="p-2.5 rounded-lg bg-neutral-950/70 border border-neutral-800/80">
          <span className="text-[10px] text-neutral-400 block mb-0.5">Retained Basin Volume</span>
          <span className="text-sm font-bold text-neutral-100">{manhole.stored_vol_m3} <span className="text-xs font-normal text-neutral-400">m³</span></span>
        </div>

        <div className="p-2.5 rounded-lg bg-neutral-950/70 border border-neutral-800/80">
          <span className="text-[10px] text-neutral-400 block mb-0.5">Ground Elevation</span>
          <span className="text-sm font-bold text-neutral-100">{manhole.elevation_m} <span className="text-xs font-normal text-neutral-400">m AMSL</span></span>
        </div>

        <div className="p-2.5 rounded-lg bg-neutral-950/70 border border-neutral-800/80">
          <span className="text-[10px] text-neutral-400 block mb-0.5">Building Coverage</span>
          <span className="text-sm font-bold text-neutral-100">{manhole.building_pct} <span className="text-xs font-normal text-neutral-400">%</span></span>
        </div>

        <div className="p-2.5 rounded-lg bg-neutral-950/70 border border-neutral-800/80">
          <span className="text-[10px] text-neutral-400 block mb-0.5">Contributing Area</span>
          <span className="text-sm font-bold text-neutral-100">{manhole.effective_area_m2} <span className="text-xs font-normal text-neutral-400">m²</span></span>
        </div>

        <div className="p-2.5 rounded-lg bg-neutral-950/70 border border-neutral-800/80">
          <span className="text-[10px] text-neutral-400 block mb-0.5">Connected Conduits</span>
          <span className="text-sm font-bold text-neutral-100">{manhole.connected_pipes} <span className="text-xs font-normal text-neutral-400">pipes</span></span>
        </div>
      </div>

      {/* Action Buttons: Set as Start / Destination */}
      {(onSetStart || onSetDestination) && (
        <div className="grid grid-cols-2 gap-2 mt-3 pt-3 border-t border-neutral-800">
          {onSetStart && (
            <button
              onClick={() => onSetStart(manhole.id)}
              className="px-2.5 py-1.5 rounded-lg bg-emerald-950/60 hover:bg-emerald-900/80 border border-emerald-700/60 text-emerald-300 text-xs font-medium flex items-center justify-center gap-1 transition-all"
            >
              <span>Set as Start 🟢</span>
            </button>
          )}
          {onSetDestination && (
            <button
              onClick={() => onSetDestination(manhole.id)}
              className="px-2.5 py-1.5 rounded-lg bg-red-950/60 hover:bg-red-900/80 border border-red-700/60 text-red-300 text-xs font-medium flex items-center justify-center gap-1 transition-all"
            >
              <span>Set as End 🔴</span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
