"""
backend/simulator/generate_scenarios.py — Rainfall Scenario Generator.

Produces hyetographs (intensity_mm_hr over times_min) for:
  1. Bulk Synthetic Training Set:
       Latin Hypercube Sampling (LHS) across 4 parameters:
         - peak_intensity_mm_hr: 6 to 100 mm/hr (skewed via power transform to avoid severe underprediction)
         - duration_min: 30 to 180 min
         - peak_timing_ratio (r): 0.2 to 0.6
         - decay_exponent (n): 0.5 to 0.8
       Chicago-method hyetograph generation with closed-form peak anchoring.
  2. Historical Replay Scenarios (Validation / Test ONLY):
       - Sept 2025 Kolkata storm (HIGH confidence, 4-segment documented reconstruction, 234.7mm total).
       - 2021 Kolkata storm (LOWER confidence, documented 98mm peak hour with documented 50/50 split assumption).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

# Compatible with both NumPy 1.x (np.trapz) and NumPy 2.x (np.trapezoid)
_integrate_trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))


@dataclass
class ScenarioParams:
    scenario_id: str
    source: str  # "synthetic_lhs" or "historical_replay"
    peak_intensity_mm_hr: float
    duration_min: float
    peak_timing_ratio: float  # r in [0, 1]
    decay_exponent: float     # n in [0, 1]
    total_depth_mm: float
    times_min: np.ndarray = field(repr=False)
    intensity_mm_hr: np.ndarray = field(repr=False)
    metadata: Dict = field(default_factory=dict)


def _skew_toward_upper(u: np.ndarray, power: float = 0.6) -> np.ndarray:
    """
    Applies a power transform to skew uniform LHS samples toward the upper end.
    With power=0.6, samples cluster more densely in the 40-100 mm/hr range
    to counter severe-node class imbalance.
    """
    return u ** power


def chicago_hyetograph(
    duration_min: float,
    peak_intensity_mm_hr: float,
    peak_timing_ratio: float = 0.35,
    decay_exponent: float = 0.65,
    b_min: float = 5.0,
    dt_min: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Generates a continuous Chicago-method hyetograph anchored directly to peak intensity.

    Formulation:
      Anchored parameter: a = i_peak * b_min^n
      For t <= t_peak:
        i(t) = a * [(1 - n) * (t_peak - t)/r + b] / [(t_peak - t)/r + b]^(1 + n)
      For t > t_peak:
        i(t) = a * [(1 - n) * (t - t_peak)/(1 - r) + b] / [(t - t_peak)/(1 - r) + b]^(1 + n)
    """
    times_min = np.arange(0.0, duration_min + dt_min / 2.0, dt_min)
    t_peak = duration_min * peak_timing_ratio
    r = np.clip(peak_timing_ratio, 0.05, 0.95)
    n = np.clip(decay_exponent, 0.1, 0.95)

    a = peak_intensity_mm_hr * (b_min ** n)

    intensity = np.zeros_like(times_min)

    # Before peak (t <= t_peak)
    pre_mask = times_min <= t_peak
    t_pre = times_min[pre_mask]
    delta_pre = (t_peak - t_pre) / r + b_min
    intensity[pre_mask] = a * ((1.0 - n) * (t_peak - t_pre) / r + b_min) / (delta_pre ** (1.0 + n))

    # After peak (t > t_peak)
    post_mask = times_min > t_peak
    t_post = times_min[post_mask]
    delta_post = (t_post - t_peak) / (1.0 - r) + b_min
    intensity[post_mask] = a * ((1.0 - n) * (t_post - t_peak) / (1.0 - r) + b_min) / (delta_post ** (1.0 + n))

    # Total accumulated rainfall depth (mm) via trapezoidal integration
    # intensity in mm/hr, dt in hours -> depth in mm
    total_depth_mm = float(_integrate_trapz(intensity, times_min / 60.0))

    return times_min, intensity, total_depth_mm


def resample_to_simulator_dt(
    times_min: np.ndarray,
    intensity_mm_hr: np.ndarray,
    dt_sec: float = 10.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Resamples rainfall time series to the discrete simulator timestep (dt_sec).

    Returns:
        sim_times_sec: [T] array in seconds
        sim_rain_mm_hr: [T] array of rainfall rates
    """
    total_sec = times_min[-1] * 60.0
    sim_times_sec = np.arange(0.0, total_sec + dt_sec / 2.0, dt_sec)
    sim_times_min = sim_times_sec / 60.0

    sim_rain_mm_hr = np.interp(sim_times_min, times_min, intensity_mm_hr)
    return sim_times_sec, sim_rain_mm_hr


def generate_lhs_scenarios(n_scenarios: int = 200, seed: int = 42) -> List[ScenarioParams]:
    """
    Generates n_scenarios Latin Hypercube sampled synthetic storm scenarios.
    """
    rng = np.random.default_rng(seed)

    # 4 parameters: [peak_intensity, duration, peak_timing_ratio, decay_exponent]
    # Latin hypercube interval partitioning
    lhs_samples = np.zeros((n_scenarios, 4))
    for dim in range(4):
        perm = rng.permutation(n_scenarios)
        sub_intervals = (perm + rng.uniform(0.0, 1.0, size=n_scenarios)) / n_scenarios
        lhs_samples[:, dim] = sub_intervals

    # 1. Peak Intensity: 6 to 100 mm/hr (skewed toward upper-middle)
    skewed_intensity_u = _skew_toward_upper(lhs_samples[:, 0], power=0.6)
    peak_intensities = 6.0 + skewed_intensity_u * (100.0 - 6.0)

    # 2. Duration: 30 to 180 minutes
    durations = 30.0 + lhs_samples[:, 1] * (180.0 - 30.0)

    # 3. Peak timing ratio (r): 0.20 to 0.60
    r_ratios = 0.20 + lhs_samples[:, 2] * (0.60 - 0.20)

    # 4. Decay exponent (n): 0.50 to 0.80
    decay_exponents = 0.50 + lhs_samples[:, 3] * (0.80 - 0.50)

    scenarios = []
    for i in range(n_scenarios):
        sc_id = f"lhs_{i+1:03d}"
        dur = float(durations[i])
        i_peak = float(peak_intensities[i])
        r = float(r_ratios[i])
        n = float(decay_exponents[i])

        t_min, i_series, tot_depth = chicago_hyetograph(
            duration_min=dur,
            peak_intensity_mm_hr=i_peak,
            peak_timing_ratio=r,
            decay_exponent=n,
            dt_min=0.5
        )

        sc = ScenarioParams(
            scenario_id=sc_id,
            source="synthetic_lhs",
            peak_intensity_mm_hr=round(i_peak, 2),
            duration_min=round(dur, 1),
            peak_timing_ratio=round(r, 3),
            decay_exponent=round(n, 3),
            total_depth_mm=round(tot_depth, 2),
            times_min=t_min,
            intensity_mm_hr=i_series,
            metadata={"sampling": "latin_hypercube", "skew_power": 0.6}
        )
        scenarios.append(sc)

    return scenarios


def generate_transition_lhs_scenarios(
    n_scenarios: int = 60,
    intensity_range: Tuple[float, float] = (30.0, 70.0),
    duration_range: Tuple[float, float] = (30.0, 180.0),
    peak_ratio_range: Tuple[float, float] = (0.20, 0.60),
    decay_range: Tuple[float, float] = (0.40, 0.80),
    seed: int = 9999,
) -> List[ScenarioParams]:
    """
    Generates LHS scenarios targeted specifically at the 30-70 mm/hr transition band
    with uniform (unskewed) sampling to densify the flooding boundary dataset.
    """
    rng = np.random.default_rng(seed)

    perm_i = rng.permutation(n_scenarios)
    perm_dur = rng.permutation(n_scenarios)
    perm_r = rng.permutation(n_scenarios)
    perm_n = rng.permutation(n_scenarios)

    scenarios = []
    for k in range(n_scenarios):
        sc_id = f"lhs_transition_{k+1:03d}"

        u_i = (perm_i[k] + rng.uniform(0.0, 1.0)) / n_scenarios
        u_dur = (perm_dur[k] + rng.uniform(0.0, 1.0)) / n_scenarios
        u_r = (perm_r[k] + rng.uniform(0.0, 1.0)) / n_scenarios
        u_n = (perm_n[k] + rng.uniform(0.0, 1.0)) / n_scenarios

        # Uniform sampling within 30-70 mm/hr (no skew)
        i_peak = intensity_range[0] + u_i * (intensity_range[1] - intensity_range[0])
        dur = duration_range[0] + u_dur * (duration_range[1] - duration_range[0])
        r = peak_ratio_range[0] + u_r * (peak_ratio_range[1] - peak_ratio_range[0])
        n = decay_range[0] + u_n * (decay_range[1] - decay_range[0])

        t_min, i_series, tot_depth = chicago_hyetograph(
            duration_min=dur,
            peak_intensity_mm_hr=i_peak,
            peak_timing_ratio=r,
            decay_exponent=n,
            dt_min=0.5
        )

        sc = ScenarioParams(
            scenario_id=sc_id,
            source="synthetic_lhs",
            peak_intensity_mm_hr=round(i_peak, 2),
            duration_min=round(dur, 1),
            peak_timing_ratio=round(r, 3),
            decay_exponent=round(n, 3),
            total_depth_mm=round(tot_depth, 2),
            times_min=t_min,
            intensity_mm_hr=i_series,
            metadata={"sampling": "transition_latin_hypercube", "target_band": "30-70mm_hr"}
        )
        scenarios.append(sc)

    return scenarios


def build_historical_scenarios() -> List[ScenarioParams]:
    """
    Builds the two documented historical storm replay scenarios for validation/testing.
    """
    scenarios = []

    # ── 1. Sept 2025 Kolkata Cloudburst (HIGH Confidence) ──
    # Documented 4 segments: 3hr moderate (48.6mm), then 3hr intense (60mm + 98mm + 27.6mm) = 234.2mm total
    t_list = []
    i_list = []

    # Segment 1: 0 to 180 min (3hr) @ 16.2 mm/hr (48.6mm)
    t_seg1 = np.linspace(0.0, 180.0, 181)
    i_seg1 = np.full_like(t_seg1, fill_value=16.2)
    t_list.append(t_seg1)
    i_list.append(i_seg1)

    # Segment 2: 180 to 240 min (1hr) sustained @ 60.0 mm/hr (60.0mm)
    t_seg2 = np.linspace(180.0, 240.0, 61)[1:]
    i_seg2 = np.full_like(t_seg2, fill_value=60.0)
    t_list.append(t_seg2)
    i_list.append(i_seg2)

    # Segment 3: 240 to 300 min (1hr) near-cloudburst peak @ 98.0 mm/hr (98.0mm)
    t_seg3 = np.linspace(240.0, 300.0, 61)[1:]
    i_seg3 = np.full_like(t_seg3, fill_value=98.0)
    t_list.append(t_seg3)
    i_list.append(i_seg3)

    # Segment 4: 300 to 360 min (1hr) remainder @ 27.6 mm/hr (27.6mm)
    t_seg4 = np.linspace(300.0, 360.0, 61)[1:]
    i_seg4 = np.full_like(t_seg4, fill_value=27.6)
    t_list.append(t_seg4)
    i_list.append(i_seg4)

    t_sept25 = np.concatenate(t_list)
    i_sept25 = np.concatenate(i_list)
    tot_sept25 = float(_integrate_trapz(i_sept25, t_sept25 / 60.0))

    sc_sept25 = ScenarioParams(
        scenario_id="historical_sept_2025",
        source="historical_replay",
        peak_intensity_mm_hr=98.0,
        duration_min=360.0,
        peak_timing_ratio=270.0 / 360.0,
        decay_exponent=0.0,
        total_depth_mm=round(tot_sept25, 2),
        times_min=t_sept25,
        intensity_mm_hr=i_sept25,
        metadata={
            "event": "Kolkata September 2025 Cloudburst",
            "confidence": "HIGH (Segment-documented)",
            "documented_total_mm": 234.2
        }
    )
    scenarios.append(sc_sept25)

    # ── 2. 2021 Kolkata Monsoon Storm (LOWER Confidence — documented 50/50 split assumption) ──
    # Documented 251.4mm over 7hr (420 min), 98mm peak hour (3-4am, t=180-240 min).
    # Remaining 153.4mm split 50/50: 76.7mm in pre-peak 3hr (25.57 mm/hr) and 76.7mm in post-peak 3hr (25.57 mm/hr).
    t2_list = []
    i2_list = []

    # Pre-peak: 0 to 180 min @ 25.57 mm/hr (76.7mm)
    t2_seg1 = np.linspace(0.0, 180.0, 181)
    i2_seg1 = np.full_like(t2_seg1, fill_value=25.57)
    t2_list.append(t2_seg1)
    i2_list.append(i2_seg1)

    # Peak: 180 to 240 min @ 98.0 mm/hr (98.0mm)
    t2_seg2 = np.linspace(180.0, 240.0, 61)[1:]
    i2_seg2 = np.full_like(t2_seg2, fill_value=98.0)
    t2_list.append(t2_seg2)
    i2_list.append(i2_seg2)

    # Post-peak: 240 to 420 min @ 25.57 mm/hr (76.7mm)
    t2_seg3 = np.linspace(240.0, 420.0, 181)[1:]
    i2_seg3 = np.full_like(t2_seg3, fill_value=25.57)
    t2_list.append(t2_seg3)
    i2_list.append(i2_seg3)

    t_2021 = np.concatenate(t2_list)
    i_2021 = np.concatenate(i2_list)
    tot_2021 = float(_integrate_trapz(i_2021, t_2021 / 60.0))

    sc_2021 = ScenarioParams(
        scenario_id="historical_2021",
        source="historical_replay",
        peak_intensity_mm_hr=98.0,
        duration_min=420.0,
        peak_timing_ratio=210.0 / 420.0,
        decay_exponent=0.0,
        total_depth_mm=round(tot_2021, 2),
        times_min=t_2021,
        intensity_mm_hr=i_2021,
        metadata={
            "event": "Kolkata 2021 Extreme Storm",
            "confidence": "LOWER (Documented 98mm peak hour; 50/50 remainder assumption)",
            "documented_total_mm": 251.4
        }
    )
    scenarios.append(sc_2021)

    return scenarios


if __name__ == "__main__":
    print("── Testing Rainfall Scenario Generator ──")
    lhs_scs = generate_lhs_scenarios(n_scenarios=200)
    print(f"Generated {len(lhs_scs)} Latin Hypercube scenarios.")
    peaks = [s.peak_intensity_mm_hr for s in lhs_scs]
    durs = [s.duration_min for s in lhs_scs]
    depths = [s.total_depth_mm for s in lhs_scs]
    print(f"  Peak Intensity range: {min(peaks):.1f} to {max(peaks):.1f} mm/hr (mean: {np.mean(peaks):.1f})")
    print(f"  Duration range:       {min(durs):.1f} to {max(durs):.1f} min (mean: {np.mean(durs):.1f})")
    print(f"  Total Depth range:    {min(depths):.1f} to {max(depths):.1f} mm (mean: {np.mean(depths):.1f})")

    hist_scs = build_historical_scenarios()
    print(f"\nGenerated {len(hist_scs)} Historical Replay Scenarios:")
    for h in hist_scs:
        print(f"  [{h.scenario_id}] Total Depth: {h.total_depth_mm:.1f} mm | Peak: {h.peak_intensity_mm_hr:.1f} mm/hr | Duration: {h.duration_min:.0f} min")
