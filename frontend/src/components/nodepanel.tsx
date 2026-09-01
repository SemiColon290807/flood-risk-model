import { X } from "lucide-react";
import type { RoadSegmentProperties } from "../types/flood";
import { getDepthLabel } from "../utils/waterDepthLabel";

interface NodePanelProps {
  node: RoadSegmentProperties;
  onClose: () => void;
}

export default function NodePanel({ node, onClose }: NodePanelProps) {
  return (
    <div className="absolute bottom-6 right-6 z-30 w-80 rounded-xl bg-neutral-900/95 border border-neutral-800 p-4 text-neutral-100 shadow-2xl backdrop-blur-md transition-all animate-in fade-in slide-in-from-bottom-2">
      <div className="flex items-center justify-between mb-2">
        <div>
          <div className="text-sm font-bold">Road Segment {node.id}</div>
          <div className="text-[11px] text-neutral-400">
            Nodes {node.from} → {node.to}
          </div>
        </div>
        <button onClick={onClose} className="p-1 text-neutral-400 hover:text-white rounded-lg hover:bg-neutral-800">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="mt-3 p-3.5 rounded-xl bg-neutral-950 border border-neutral-800">
        <div className="text-xs text-neutral-400 uppercase tracking-wide">
          Surface Water Depth
        </div>
        <div className="text-3xl font-black text-white mt-1 flex items-baseline gap-2">
          {node.depth_cm}
          <span className="text-sm font-medium text-neutral-400">cm</span>
        </div>
        <div className="text-xs text-neutral-300 mt-1">
          {getDepthLabel(node.depth_cm)} (avg. adult reference)
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-800">
          <div className="text-neutral-400 text-[11px]">Rainfall (Accum.)</div>
          <div className="text-white font-semibold mt-0.5">
            {node.rainfall_mm} <span className="text-neutral-400 font-normal">mm</span>
          </div>
        </div>
        <div className="p-2.5 rounded-lg bg-neutral-950 border border-neutral-800">
          <div className="text-neutral-400 text-[11px]">Inflow / Capacity</div>
          <div className="text-white font-semibold mt-0.5 truncate">
            {node.inflow_rate} / {node.pipe_capacity} <span className="text-neutral-400 font-normal">m³/s</span>
          </div>
        </div>
      </div>

      {node.blocked && (
        <div className="mt-3 text-xs text-red-400 font-semibold flex items-center gap-1.5 p-2 rounded-lg bg-red-950/40 border border-red-900/50">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
          Manually flagged as blocked (0% capacity)
        </div>
      )}
    </div>
  );
}