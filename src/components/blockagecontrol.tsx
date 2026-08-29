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

  return (
    <div className="absolute top-24 right-6 z-20 w-64 rounded-xl bg-neutral-900 border border-neutral-800 p-4 text-neutral-100 shadow-xl">
      <div className="text-sm font-bold mb-3">Admin: Report Blockage</div>

      <label className="text-xs text-neutral-400">Road segment</label>
      <select
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        className="w-full mb-3 rounded-md bg-neutral-950 border border-neutral-800 text-sm p-1.5"
      >
        {ROAD_EDGES.map((r) => (
          <option key={r.id} value={r.id}>
            {r.id} ({r.from} → {r.to})
          </option>
        ))}
      </select>

      <button
        onClick={toggleBlockage}
        className={`w-full text-sm font-semibold py-1.5 rounded-md ${
          isBlocked ? "bg-neutral-700 hover:bg-neutral-600" : "bg-red-600 hover:bg-red-500"
        }`}
      >
        {isBlocked ? "Clear Blockage" : "Mark as Blocked"}
      </button>
    </div>
  );
}