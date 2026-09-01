import { useState } from "react";
import { ROAD_EDGES } from "../data/roadNetwork";

interface BlockageControlProps {
  blockedRoadIds: Set<string>;
  setBlockedRoadIds: (ids: Set<string>) => void;
}

export default function BlockageControl({
  blockedRoadIds,
  setBlockedRoadIds,
}: BlockageControlProps) {
  const [isCollapsed, setIsCollapsed] = useState<boolean>(true);
  const [selected, setSelected] = useState(ROAD_EDGES[0].id);
  const isBlocked = blockedRoadIds.has(selected);

  const toggleBlockage = () => {
    const next = new Set(blockedRoadIds);
    if (isBlocked) {
      next.delete(selected);
    } else {
      next.add(selected);
    }
    setBlockedRoadIds(next);
  };

  const removeBlockage = (id: string) => {
    const next = new Set(blockedRoadIds);
    next.delete(id);
    setBlockedRoadIds(next);
  };

  if (isCollapsed) {
    return (
      <button
        onClick={() => setIsCollapsed(false)}
        className="absolute top-16 right-6 z-20 px-3.5 py-2 rounded-xl bg-neutral-900/90 hover:bg-neutral-800 border border-neutral-800 text-neutral-200 shadow-xl backdrop-blur-md text-xs font-semibold flex items-center gap-2 transition-all hover:scale-105"
        title="Open Admin Road Blockage Controls"
      >
        <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
        <span>🚧 Report Blockage</span>
        {blockedRoadIds.size > 0 && (
          <span className="bg-red-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">
            {blockedRoadIds.size} active
          </span>
        )}
      </button>
    );
  }

  return (
    <div className="absolute top-16 right-6 z-20 w-72 rounded-xl bg-neutral-900/95 border border-neutral-800 p-4 text-neutral-100 shadow-2xl backdrop-blur-md transition-all">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-bold flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-red-500" />
          Admin: Road Blockage
        </div>
        <button
          onClick={() => setIsCollapsed(true)}
          className="text-neutral-400 hover:text-white text-xs px-2 py-0.5 rounded-md hover:bg-neutral-800 transition-colors"
          title="Minimize Panel"
        >
          ✕
        </button>
      </div>

      <label className="text-[11px] text-neutral-400 block mb-1">Target Road Segment</label>
      <select
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        className="w-full mb-3 rounded-lg bg-neutral-950 border border-neutral-800 text-xs p-2 text-neutral-200"
      >
        {ROAD_EDGES.slice(0, 150).map((r) => (
          <option key={r.id} value={r.id}>
            {r.id} ({r.from} → {r.to})
          </option>
        ))}
      </select>

      <button
        onClick={toggleBlockage}
        className={`w-full text-xs font-semibold py-2 rounded-lg transition-all ${
          isBlocked
            ? "bg-neutral-800 hover:bg-neutral-700 text-neutral-200 border border-neutral-700"
            : "bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/30"
        }`}
      >
        {isBlocked ? "Clear Selected Blockage" : "Mark Segment as Blocked"}
      </button>

      {/* Active Blockages List */}
      {blockedRoadIds.size > 0 && (
        <div className="mt-3 pt-3 border-t border-neutral-800">
          <div className="text-[11px] text-neutral-400 mb-1.5 flex items-center justify-between">
            <span>Active Blockades ({blockedRoadIds.size})</span>
          </div>
          <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
            {Array.from(blockedRoadIds).map((id) => (
              <span
                key={id}
                onClick={() => removeBlockage(id)}
                className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-md bg-red-950/80 border border-red-800/80 text-red-300 cursor-pointer hover:bg-red-900 transition-colors"
                title="Click to unblock"
              >
                <span>{id}</span>
                <span className="font-bold text-red-400">×</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}