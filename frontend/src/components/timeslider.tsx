import { useEffect } from "react";
import { Play, Pause } from "lucide-react";

interface TimeSliderProps {
  timestep: number;
  setTimestep: (fn: (prev: number) => number) => void;
  isPlaying: boolean;
  setIsPlaying: (p: boolean) => void;
}

const STEP_MINUTES = 10;
const MAX_STEP = 18; // 18 * 10 = 180 minutes = 3 hours

export default function TimeSlider({ timestep, setTimestep, isPlaying, setIsPlaying }: TimeSliderProps) {
  const formatTime = (step: number) => {
    const totalMinutes = step * STEP_MINUTES;
    const hours = Math.floor(totalMinutes / 60);
    const mins = totalMinutes % 60;
    return `+${hours}h ${mins.toString().padStart(2, "0")}m`;
  };

  useEffect(() => {
    if (!isPlaying) return;
    const timer = window.setInterval(() => {
      setTimestep((prev) => (prev >= MAX_STEP ? 0 : prev + 1));
    }, 500);
    return () => clearInterval(timer);
  }, [isPlaying]);

  return (
    <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-10 w-[90%] max-w-2xl bg-neutral-900/95 backdrop-blur-md border border-neutral-800 rounded-2xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className="p-2 bg-neutral-800 hover:bg-neutral-700 text-white rounded-lg"
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          </button>
          <span className="text-sm font-semibold tracking-wider text-emerald-400">
            {formatTime(timestep)}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs text-neutral-400">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Safe</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-yellow-500" /> Caution</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-orange-500" /> Moderate</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" /> Severe (&gt;30cm)</span>
        </div>
      </div>

      <input
        type="range"
        min="0"
        max={MAX_STEP}
        step="1"
        value={timestep}
        onChange={(e) => setTimestep(() => Number(e.target.value))}
        className="w-full accent-emerald-500 bg-neutral-800 h-2 rounded-lg cursor-pointer"
      />
      <div className="flex justify-between text-[10px] text-neutral-500 mt-1">
        <span>Now (t=0)</span>
        <span>+1.5 Hours</span>
        <span>+3.0 Hours</span>
      </div>
    </div>
  );
}