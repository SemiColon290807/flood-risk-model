"""
docs/generate_presentation_charts.py
High-Aesthetic, Publication/Keynote-Quality Presentation Charts for Hackathon Slide Deck.

Chart 1: Premium Speed Benchmark (GConvGRU Neural Surrogate vs Vectorized Physics vs Industry Solvers)
Chart 2: Severe Flooding Hit-Rate by Storm Intensity
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, Rectangle
import matplotlib.ticker as ticker
from pathlib import Path

DOCS_DIR = Path("/Users/macbook/Code_Masterfile/Flood Risk Model/flood-risk-model/docs")
DOCS_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACTS_DIR = Path("/Users/macbook/.gemini/antigravity-ide/brain/d3f847ae-d693-4664-8da7-2370c64865f8")


# =====================================================================
#  CHART 1 — ULTRA-AESTHETIC KEYNOTE BENCHMARK CHART
# =====================================================================
def generate_chart_1():
    # 16:9 Presentation Canvas (14.22 x 8.0 inches @ 300 DPI)
    fig, ax = plt.subplots(figsize=(14.22, 8.0), dpi=300)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")

    tiers = [
        {
            "y": 0,
            "title": "Spatiotemporal Neural Surrogate",
            "subtitle": "GConvGRU Recurrent Graph Network · 4.18 ms / step (PyTorch GNN)",
            "time_sec": 1.51,
            "display_time": "1.51 s",
            "badge": "⚡ ~1,500× FASTER",
            "badge_color": "#4338ca",
            "badge_bg": "#eef2ff",
            "badge_edge": "#6366f1",
            "bar_color": "#6366f1",
            "bar_edge": "#4f46e5",
            "tag": "Instantaneous AI Rollout",
        },
        {
            "y": 1,
            "title": "Vectorized Physics Simulator",
            "subtitle": "2D Dual-Porosity Explicit Solver · 5.50 ms / step (1,080 timesteps)",
            "time_sec": 5.94,
            "display_time": "5.94 s",
            "badge": "⚡ ~380× FASTER",
            "badge_color": "#0369a1",
            "badge_bg": "#f0f9ff",
            "badge_edge": "#0284c7",
            "bar_color": "#0284c7",
            "bar_edge": "#0369a1",
            "tag": "Real-Time Physical Nowcast",
        },
        {
            "y": 2,
            "title": "Industry 2D Hydraulic Solvers",
            "subtitle": "SWMM 2D / MIKE 21 / HEC-RAS 2D · Implicit Navier-Stokes Matrix Inversion",
            "time_sec": 2250.0,
            "display_time": "37.5 min (30–45m)",
            "badge": "BASELINE (1×)",
            "badge_color": "#475569",
            "badge_bg": "#f8fafc",
            "badge_edge": "#94a3b8",
            "bar_color": "#94a3b8",
            "bar_edge": "#64748b",
            "tag": "Offline Planning Only",
        },
    ]

    # Logarithmic x-scale
    ax.set_xscale("log")
    ax.set_xlim(0.35, 48000.0)
    ax.set_ylim(-0.65, 2.75)

    # Clean axes: hide all box spines
    for s in ax.spines.values():
        s.set_visible(False)

    # Vertical reference lines at human-readable milestones
    milestones = [1, 10, 60, 600, 3600]
    milestone_labels = ["1 sec", "10 sec", "1 min", "10 min", "1 hour"]
    
    for x_val in milestones:
        ax.axvline(x=x_val, color="#f1f5f9", linestyle="-", linewidth=1.5, zorder=1)
        ax.axvline(x=x_val, color="#e2e8f0", linestyle=":", linewidth=0.8, zorder=1)

    bar_height = 0.36

    # Background card tracks for each tier (spans entire width)
    for tier in tiers:
        y = tier["y"]
        ax.barh(
            y, 46500.0,
            height=bar_height,
            left=0.35,
            color="#f8fafc",
            edgecolor="#f1f5f9",
            linewidth=1.0,
            zorder=2
        )

    # Foreground colored value bars
    for tier in tiers:
        y = tier["y"]
        ax.barh(
            y, tier["time_sec"] - 0.35,
            height=bar_height,
            left=0.35,
            color=tier["bar_color"],
            edgecolor=tier["bar_edge"],
            linewidth=1.5,
            zorder=3
        )

    # Industry solver error bar (30 min = 1800s to 45 min = 2700s)
    ax.errorbar(
        [2250.0], [2],
        xerr=[[450], [450]],
        fmt="none",
        ecolor="#0f172a",
        elinewidth=2.2,
        capsize=7,
        capthick=2.2,
        zorder=4,
    )

    # Typography & Annotations for each tier
    for tier in tiers:
        y = tier["y"]

        # 1. Tier Headline (Above bar)
        ax.text(
            0.38, y + 0.30,
            tier["title"],
            fontsize=13.5,
            fontweight="bold",
            color="#0f172a",
            va="bottom",
            ha="left",
            zorder=5
        )

        # 2. Tier Subtitle (Under headline)
        ax.text(
            0.38, y + 0.20,
            tier["subtitle"],
            fontsize=10.0,
            fontweight="medium",
            color="#64748b",
            va="bottom",
            ha="left",
            zorder=5
        )

        # 3. Time Value & Badge placement
        if tier["y"] == 0:
            val_x = 2.2
            badge_x = 24.0
            display_txt = tier["display_time"]
            tag_txt = tier["tag"]
        elif tier["y"] == 1:
            val_x = 8.5
            badge_x = 95.0
            display_txt = tier["display_time"]
            tag_txt = tier["tag"]
        else: # Industry
            val_x = 3050.0
            badge_x = 16000.0
            display_txt = "37.5 min"
            tag_txt = "30–45m range · Offline Only"

        # Exact time text (stacked top)
        ax.text(
            val_x, y + 0.02,
            display_txt,
            fontsize=13.5,
            fontweight="bold",
            color=tier["bar_edge"] if tier["y"] < 2 else "#1e293b",
            va="bottom",
            ha="left",
            zorder=5
        )

        # Status Tag under time (stacked bottom)
        ax.text(
            val_x, y - 0.02,
            tag_txt,
            fontsize=9.0,
            fontweight="semibold",
            color="#64748b",
            va="top",
            ha="left",
            zorder=5
        )

        # Speedup pill badge (centered vertically)
        badge_props = dict(
            boxstyle="round,pad=0.45,rounding_size=0.35",
            facecolor=tier["badge_bg"],
            edgecolor=tier["badge_edge"],
            linewidth=1.2,
            alpha=0.98
        )

        ax.text(
            badge_x, y,
            tier["badge"],
            fontsize=10.5,
            fontweight="bold",
            color=tier["badge_color"],
            va="center",
            ha="left",
            bbox=badge_props,
            zorder=5
        )

    # Bottom Axis & Ticks
    ax.set_yticks([])
    ax.set_xticks(milestones)
    ax.set_xticklabels(milestone_labels, fontsize=11, fontweight="semibold", color="#475569")
    ax.tick_params(axis="x", length=6, width=1.2, color="#cbd5e1", pad=8)

    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_linewidth(1.2)
    ax.spines["bottom"].set_color("#cbd5e1")

    ax.set_xlabel(
        "Time Required to Simulate Full 3-Hour Storm across 8,001 Nodes (Logarithmic Scale — Shorter is Faster)",
        fontsize=11.5,
        fontweight="bold",
        color="#334155",
        labelpad=14
    )

    # ── HEADER SECTION (Keynote Polish) ─────────────────────────────
    cat_props = dict(
        boxstyle="round,pad=0.35,rounding_size=0.3",
        facecolor="#f1f5f9",
        edgecolor="#cbd5e1",
        linewidth=1.0
    )
    fig.text(
        0.065, 0.945,
        "PERFORMANCE BENCHMARK  ·  8,001 JUNCTIONS  ·  14,344 CONDUITS",
        fontsize=9.5,
        fontweight="bold",
        color="#475569",
        bbox=cat_props
    )

    fig.text(
        0.065, 0.895,
        "Sub-2-Second Neural Flood Nowcasting",
        fontsize=20,
        fontweight="bold",
        color="#0f172a"
    )

    fig.text(
        0.065, 0.855,
        "Comparing end-to-end 3-hour pluvial storm simulation runtime across Kolkata Delta testbed (JU Zone)",
        fontsize=11.5,
        color="#64748b"
    )

    plt.subplots_adjust(left=0.065, right=0.96, top=0.82, bottom=0.13)

    # Save to docs and artifacts
    for dest in (DOCS_DIR, ARTIFACTS_DIR):
        out = dest / "chart1_simulation_speed_comparison.png"
        fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
        print(f"  → Saved: {out}")
    plt.close(fig)


# =====================================================================
#  CHART 2 — SEVERE FLOODING HIT-RATE BY STORM INTENSITY
# =====================================================================
def generate_chart_2():
    fig, ax = plt.subplots(figsize=(14.22, 8.0), dpi=300)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    bands = ["0–30", "30–50", "50–70", "70–85", "85–100"]
    subtitles = ["Light / Moderate\n(Standard Rain)", "Heavy Frontal\n(Tipping Point)", "Severe Squall\n(High Hazard)", "Cloudburst\n(Urban Gridlock)", "Extreme Deluge\n(Catastrophic)"]
    hit_rates = [4.3, 48.0, 90.0, 97.8, 100.0]
    fractions = ["1 / 23", "36 / 75", "72 / 80", "44 / 45", "37 / 37"]

    x = np.arange(len(bands))

    # Color Palette: Modern Risk Gradient
    fills = ["#10b981", "#f59e0b", "#f97316", "#ef4444", "#991b1b"]
    edges = ["#059669", "#d97706", "#ea580c", "#dc2626", "#7f1d1d"]

    # Background Card Bars
    for i in range(len(bands)):
        ax.bar(
            x[i], 115,
            width=0.55,
            color="#f8fafc",
            edgecolor="#f1f5f9",
            linewidth=1.0,
            zorder=1
        )

    # Foreground Value Bars
    bars = ax.bar(
        x, hit_rates,
        width=0.55,
        color=fills,
        edgecolor=edges,
        linewidth=1.6,
        zorder=3
    )

    # Clean Grid & Spines
    ax.grid(axis="y", linestyle="--", linewidth=0.7, color="#e2e8f0", alpha=0.8, zorder=0)
    ax.grid(axis="x", visible=False)

    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_linewidth(1.2)
    ax.spines["bottom"].set_color("#cbd5e1")

    # Y-axis
    ax.set_ylim(0, 125)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"], fontsize=11.5, color="#64748b")
    ax.set_ylabel("Probability of Severe Flooding (>30 cm Surface Depth)", fontsize=11.5, fontweight="bold", labelpad=12, color="#0f172a")

    # X-axis
    xlabels = [f"{b} mm/hr\n{s}" for b, s in zip(bands, subtitles)]
    ax.set_xticks(x)
    ax.set_xticklabels(xlabels, fontsize=11, fontweight="bold", color="#0f172a", linespacing=1.2)
    ax.set_xlabel("Peak Storm Rainfall Intensity Band", fontsize=12, fontweight="bold", labelpad=14, color="#0f172a")

    # Data Labels on top of each bar
    for i, bar in enumerate(bars):
        h = bar.get_height()
        cx = bar.get_x() + bar.get_width() / 2
        lbl_color = fills[i] if i > 0 else "#047857"
        
        # Percentage
        ax.text(
            cx, h + 5.0,
            f"{hit_rates[i]:.1f}%",
            ha="center", va="bottom",
            fontsize=13, fontweight="bold", color=lbl_color,
            zorder=5
        )
        # Fraction
        ax.text(
            cx, h + 2.0,
            f"({fractions[i]} scenarios)",
            ha="center", va="bottom",
            fontsize=9.0, color="#64748b",
            zorder=5
        )

    # Inflection Callout Annotation
    ax.annotate(
        "HYDRAULIC INFLECTION POINT\nDrainage network saturates at 30–50 mm/hr\n(Hit-rate jumps 11× from 4.3% → 48.0%)",
        xy=(1.0, 48.0), xycoords="data",
        xytext=(0.05, 88.0), textcoords="data",
        fontsize=10.5, fontweight="bold", color="#0f172a",
        arrowprops=dict(
            arrowstyle="-|>",
            color="#334155",
            lw=1.8,
            connectionstyle="arc3,rad=-0.15",
        ),
        bbox=dict(
            boxstyle="round,pad=0.55,rounding_size=0.3",
            facecolor="#f8fafc", edgecolor="#94a3b8",
            linewidth=1.2,
        ),
        zorder=6
    )

    # ── HEADER SECTION ──────────────────────────────────────────────
    cat_props = dict(
        boxstyle="round,pad=0.35,rounding_size=0.3",
        facecolor="#f1f5f9",
        edgecolor="#cbd5e1",
        linewidth=1.0
    )
    fig.text(
        0.065, 0.945,
        "EMPIRICAL RISK ANALYSIS  ·  260 LHS SCENARIOS  ·  451M OBSERVATIONS",
        fontsize=9.5,
        fontweight="bold",
        color="#475569",
        bbox=cat_props
    )

    fig.text(
        0.065, 0.895,
        "Citywide Severe Inundation Threshold",
        fontsize=20,
        fontweight="bold",
        color="#0f172a"
    )

    fig.text(
        0.065, 0.855,
        "Percentage of synthetic and historical storm scenarios triggering critical street-level inundation (>30 cm)",
        fontsize=11.5,
        color="#64748b"
    )

    plt.subplots_adjust(left=0.08, right=0.96, top=0.82, bottom=0.16)

    # Save to docs and artifacts
    for dest in (DOCS_DIR, ARTIFACTS_DIR):
        out = dest / "chart2_severe_flooding_hit_rate.png"
        fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
        print(f"  → Saved: {out}")
    plt.close(fig)


if __name__ == "__main__":
    print("Generating premium presentation charts …")
    generate_chart_1()
    generate_chart_2()
    print("All charts generated successfully.")
