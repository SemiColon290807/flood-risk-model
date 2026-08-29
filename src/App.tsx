import { useState } from "react";
import FloodMap from "./components/floodmap";
import Header from "./components/header";
import TimeSlider from "./components/timeslider";
import NodePanel from "./components/nodepanel";
import RouteOverlay from "./components/routeoverlay";
import BlockageControl from "./components/blockagecontrol";
import { getMockRoadFloodData } from "./utils/mockdata";
import { findSafeRoute } from "./utils/routing";
import type { RoadSegmentProperties, PriorityMode, RouteMode } from "./types/flood";

export default function App() {
  const [timestep, setTimestep] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [priority, setPriority] = useState<PriorityMode>("safety");
  const [selectedRoad, setSelectedRoad] = useState<RoadSegmentProperties | null>(null);

  const [blockedRoadIds, setBlockedRoadIds] = useState<Set<string>>(new Set());
  const [routeEdgeIds, setRouteEdgeIds] = useState<string[]>([]);
  const [routeFound, setRouteFound] = useState<boolean | null>(null);

  const handleFindRoute = (start: string, end: string, mode: RouteMode) => {
    const roadData = getMockRoadFloodData(timestep, blockedRoadIds);
    const result = findSafeRoute(roadData, start, end, mode);
    if (result) {
      setRouteEdgeIds(result.usedEdgeIds);
      setRouteFound(true);
    } else {
      setRouteEdgeIds([]);
      setRouteFound(false);
    }
  };

  return (
    <div className="relative w-screen h-screen bg-neutral-950 font-sans text-neutral-100 overflow-hidden">
      <FloodMap
        timestep={timestep}
        blockedRoadIds={blockedRoadIds}
        routeEdgeIds={routeEdgeIds}
        onRoadClick={setSelectedRoad}
      />
      <Header priority={priority} setPriority={setPriority} />
      <TimeSlider
        timestep={timestep}
        setTimestep={setTimestep}
        isPlaying={isPlaying}
        setIsPlaying={setIsPlaying}
      />
      <RouteOverlay onFindRoute={handleFindRoute} routeFound={routeFound} />
      <BlockageControl
        blockedRoadIds={blockedRoadIds}
        setBlockedRoadIds={setBlockedRoadIds}
      />
      {selectedRoad && (
        <NodePanel node={selectedRoad} onClose={() => setSelectedRoad(null)} />
      )}
    </div>
  );
} 