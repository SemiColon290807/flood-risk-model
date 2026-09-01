import { useState } from "react";
import { CloudRain, ChevronDown, Check } from "lucide-react";
import type { ScenarioInfo } from "../types/flood";

interface ScenarioControlProps {
  currentScenarioId: string;
  onSelectScenario: (scenarioId: string) => void;
  scenarios: ScenarioInfo[];
}

export default function ScenarioControl({
  currentScenarioId,
  onSelectScenario,
  scenarios,
}: ScenarioControlProps) {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const activeScenario = scenarios.find((s) => s.id === currentScenarioId) || scenarios[0];

  return (
    <div className="relative z-20">
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="px-3.5 py-2 rounded-xl bg-neutral-900/90 hover:bg-neutral-800 border border-neutral-800 text-neutral-100 shadow-xl backdrop-blur-md text-xs font-semibold flex items-center gap-2.5 transition-all hover:scale-105"
        title="Switch Storm Scenario"
      >
        <CloudRain className="w-4 h-4 text-blue-400" />
        <div className="text-left">
          <div className="text-[9px] text-neutral-400 uppercase tracking-wider font-medium">Storm Scenario</div>
          <div className="text-xs text-neutral-100 font-bold max-w-[180px] truncate">
            {activeScenario?.name || "Historical Scenario"}
          </div>
        </div>
        <ChevronDown className={`w-3.5 h-3.5 text-neutral-400 transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {/* Dropdown Modal */}
      {isOpen && (
        <div className="absolute top-12 right-0 w-80 rounded-xl bg-neutral-900/95 border border-neutral-800 p-3 text-neutral-100 shadow-2xl backdrop-blur-md">
          <div className="text-xs font-bold text-neutral-300 mb-2 px-1 flex items-center justify-between">
            <span>Historical Storm Scenarios</span>
            <span className="text-[10px] text-neutral-500">{scenarios.length} available</span>
          </div>

          <div className="space-y-1.5 max-h-72 overflow-y-auto pr-0.5">
            {scenarios.map((sc) => {
              const isSelected = sc.id === currentScenarioId;
              return (
                <div
                  key={sc.id}
                  onClick={() => {
                    onSelectScenario(sc.id);
                    setIsOpen(false);
                  }}
                  className={`p-2.5 rounded-lg border cursor-pointer transition-all ${
                    isSelected
                      ? "bg-blue-950/60 border-blue-500/80 shadow-md shadow-blue-950/50"
                      : "bg-neutral-950/60 hover:bg-neutral-800/80 border-neutral-800"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold text-neutral-100 flex items-center gap-1.5">
                      <span>{sc.id.startsWith("historical_2021") ? "🌀" : "🌧️"}</span>
                      <span>{sc.name}</span>
                    </span>
                    {isSelected && <Check className="w-3.5 h-3.5 text-blue-400" />}
                  </div>

                  {sc.description && (
                    <p className="text-[11px] text-neutral-400 leading-snug mb-1.5 line-clamp-2">
                      {sc.description}
                    </p>
                  )}

                  <div className="flex items-center gap-2.5 text-[10px] text-neutral-400">
                    <span className="px-1.5 py-0.5 rounded bg-neutral-900 border border-neutral-800 text-neutral-300">
                      {sc.category || "Historical Storm"}
                    </span>
                    <span>Peak: <strong className="text-neutral-200">{sc.peak_intensity_mm_hr} mm/hr</strong></span>
                    <span>Duration: <strong className="text-neutral-200">{sc.duration_hours}h</strong></span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
