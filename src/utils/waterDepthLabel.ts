export function getFloodingType(
  depth_cm: number
): "safe" | "caution" | "moderate" | "severe" {
  if (depth_cm < 5) return "safe";
  if (depth_cm < 15) return "caution";
  if (depth_cm < 30) return "moderate";
  return "severe";
}

export function getDepthLabel(depth_cm: number): string {
  if (depth_cm < 3) return "Dry / damp road";
  if (depth_cm < 10) return "Ankle deep";
  if (depth_cm < 25) return "Shin deep";
  if (depth_cm < 50) return "Knee deep";
  if (depth_cm < 90) return "Thigh deep";
  if (depth_cm < 130) return "Waist deep";
  return "Chest deep or higher";
}

export const FLOOD_COLORS: Record<string, string> = {
  safe: "#22c55e",
  caution: "#eab308",
  moderate: "#f97316",
  severe: "#ef4444",
};