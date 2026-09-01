import { useState, useEffect } from "react";
import FloodMap from "./components/floodmap";
import Header from "./components/header";
import TimeSlider from "./components/timeslider";
import NodePanel from "./components/nodepanel";
import ManholePanel from "./components/manholepanel";
import RouteOverlay from "./components/routeoverlay";
import BlockageControl from "./components/blockagecontrol";
import ScenarioControl from "./components/scenariocontrol";
import { fetchRealRoadFloodData, fetchAvailableScenarios } from "./utils/mockdata";
import { findSafeRoute, findNearestNode } from "./utils/routing";
import type { RoadSegmentProperties, ManholeProperties, PriorityMode, RouteMode, ScenarioInfo } from "./types/flood";

export default function App() {
  const [timestep, setTimestep] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [priority, setPriority] = useState<PriorityMode>("safety");
  const [showManholes, setShowManholes] = useState<boolean>(false);
  const [selectedRoad, setSelectedRoad] = useState<RoadSegmentProperties | null>(null);
  const [selectedManhole, setSelectedManhole] = useState<ManholeProperties | null>(null);

  // Storm Scenarios
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [scenarioId, setScenarioId] = useState<string>("historical_sept_2025");

  useEffect(() => {
    fetchAvailableScenarios().then(setScenarios);
  }, []);

  const [blockedRoadIds, setBlockedRoadIds] = useState<Set<string>>(new Set());
  const [startNode, setStartNode] = useState<string | null>("N7262");
  const [endNode, setEndNode] = useState<string | null>("N4613");
  const [routeMode, setRouteMode] = useState<RouteMode>("vehicle");
  const [isPickingRoute, setIsPickingRoute] = useState<boolean>(false);

  const [routeEdgeIds, setRouteEdgeIds] = useState<string[]>([]);
  const [routeFound, setRouteFound] = useState<boolean | null>(null);

  const handleFindRoute = async (start: string, end: string, mode: RouteMode) => {
    const roadData = await fetchRealRoadFloodData(timestep, blockedRoadIds, scenarioId);
    const result = findSafeRoute(roadData, start, end, mode);
    if (result) {
      setRouteEdgeIds(result.usedEdgeIds);
      setRouteFound(true);
    } else {
      setRouteEdgeIds([]);
      setRouteFound(false);
    }
  };

  const handleScenarioChange = (newScenarioId: string) => {
    setScenarioId(newScenarioId);
    setTimestep(0);
    setIsPlaying(false);
    if (startNode && endNode) {
      handleFindRoute(startNode, endNode, routeMode);
    }
  };

  const handleMapClickLocation = (lng: number, lat: number) => {
    if (!isPickingRoute) return;
    const nearest = findNearestNode(lng, lat);

    if (!startNode || (startNode && endNode)) {
      // Set new start node (Pin A) and clear old route
      setStartNode(nearest.id);
      setEndNode(null);
      setRouteEdgeIds([]);
      setRouteFound(null);
    } else if (startNode && !endNode) {
      // Set destination node (Pin B) and auto-compute safe path
      setEndNode(nearest.id);
      handleFindRoute(startNode, nearest.id, routeMode);
    }
  };

  const handleSetManholeAsStart = (nodeId: string) => {
    setStartNode(nodeId);
    setSelectedManhole(null);
    if (endNode) {
      handleFindRoute(nodeId, endNode, routeMode);
    }
  };

  const handleSetManholeAsDestination = (nodeId: string) => {
    setEndNode(nodeId);
    setSelectedManhole(null);
    if (startNode) {
      handleFindRoute(startNode, nodeId, routeMode);
    }
  };

  const handleClearRoute = () => {
    setStartNode(null);
    setEndNode(null);
    setRouteEdgeIds([]);
    setRouteFound(null);
  };

  return (
    <div className="relative w-screen h-screen bg-neutral-950 font-sans text-neutral-100 overflow-hidden">
      <FloodMap
        timestep={timestep}
        blockedRoadIds={blockedRoadIds}
        routeEdgeIds={routeEdgeIds}
        scenarioId={scenarioId}
        showManholes={showManholes}
        startNodeId={startNode}
        endNodeId={endNode}
        isPickingRoute={isPickingRoute}
        onRoadClick={(r) => {
          setSelectedRoad(r);
          setSelectedManhole(null);
        }}
        onManholeClick={(m) => {
          setSelectedManhole(m);
          setSelectedRoad(null);
        }}
        onMapClickLocation={handleMapClickLocation}
      />
      <Header
        priority={priority}
        setPriority={setPriority}
        showManholes={showManholes}
        onToggleManholes={() => setShowManholes((prev) => !prev)}
      />

      {/* Top Right Controls: Scenario Switcher & Collapsible Blockage */}
      <div className="absolute top-4 right-6 z-20 flex items-center gap-3">
        <ScenarioControl
          currentScenarioId={scenarioId}
          onSelectScenario={handleScenarioChange}
          scenarios={scenarios}
        />
      </div>

      <BlockageControl
        blockedRoadIds={blockedRoadIds}
        setBlockedRoadIds={setBlockedRoadIds}
      />

      <TimeSlider
        timestep={timestep}
        setTimestep={setTimestep}
        isPlaying={isPlaying}
        setIsPlaying={setIsPlaying}
      />

      <RouteOverlay
        start={startNode}
        setStart={setStartNode}
        end={endNode}
        setEnd={setEndNode}
        mode={routeMode}
        setMode={setRouteMode}
        isPickingRoute={isPickingRoute}
        setIsPickingRoute={setIsPickingRoute}
        onClearRoute={handleClearRoute}
        onFindRoute={handleFindRoute}
        routeFound={routeFound}
      />

      {selectedRoad && (
        <NodePanel node={selectedRoad} onClose={() => setSelectedRoad(null)} />
      )}

      {selectedManhole && (
        <ManholePanel
          manhole={selectedManhole}
          onClose={() => setSelectedManhole(null)}
          onSetStart={handleSetManholeAsStart}
          onSetDestination={handleSetManholeAsDestination}
        />
      )}
    </div>
  );
} 