import { X } from "lucide-react";
import type { RoadSegmentProperties } from "../types/flood";
import { getDepthLabel } from "../utils/waterDepthLabel";

interface NodePanelProps {
  node: RoadSegmentProperties;
  onClose: () => void;
}

export default function NodePanel({ node, onClose }: NodePanelProps) {
  return (
    <div className="absolute bottom-6 left-6 z-20 w-72 rounded-xl bg-neutral-900 border border-neutral-800 p-4 text-neutral-100 shadow-xl">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-bold">Road {node.id}</div>
        <button onClick={onClose} className="p-1 text-neutral-400 hover:text-white">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="mt-4 p-3.5 rounded-xl bg-neutral-950 border border-neutral-800">
        <div className="text-xs text-neutral-400 uppercase tracking-wide">
          Water Depth
        </div>
        <div className="text-3xl font-black text-white mt-1 flex items-baseline gap-2">
          {node.depth_cm}
          <span className="text-xs font-medium text-neutral-400">cm</span>
        </div>
        <div className="text-sm text-neutral-300 mt-1">
          {getDepthLabel(node.depth_cm)} (avg. adult reference)
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div className="p-2 rounded-lg bg-neutral-950 border border-neutral-800">
          <div className="text-neutral-400">Rainfall</div>
          <div className="text-white font-semibold">{node.rainfall_mm} mm</div>
        </div>
        <div className="p-2 rounded-lg bg-neutral-950 border border-neutral-800">
          <div className="text-neutral-400">Inflow / Capacity</div>
          <div className="text-white font-semibold">
            {node.inflow_rate} / {node.pipe_capacity}
          </div>
        </div>
      </div>

      {node.blocked && (
        <div className="mt-3 text-xs text-red-400 font-semibold">
          This road is manually flagged as blocked.
        </div>
      )}
    </div>
  );
}