"""
backend/gnn/train.py — High-Performance Training Pipeline for FloodGCN.

Features:
  1. Plain 3-layer FloodGCN surrogate architecture.
  2. SeverityWeightedLoss (upweighting surcharged nodes and active transitions).
  3. Curriculum Multi-Step Rollout Loss (unrolling 1 -> 3 -> 5 steps during training).
  4. Closed-loop multi-step autoregressive evaluation on historical storms (Sept 2025 & 2021).
"""

import os
import sys
import time
import argparse
from typing import Tuple, List, Optional, Dict
import numpy as np
import torch
import torch.nn.functional as F
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from model import FloodGCN, NUM_NODE_FEATURES, NODE_FEATURE_NAMES
from dataset import create_scenario_splits, StaticGraph, FastFloodDataset


class SeverityWeightedLoss(torch.nn.Module):
    """
    Severity-Weighted Loss to counteract the 99.6% safe vs 0.4% flood class imbalance.
    Upweights loss on:
      1. Surcharging / ponded nodes (depth > 5-10 cm)
      2. Dynamically active transitions (|Δy| > 0.5 cm)
    """
    def __init__(self, depth_weight: float = 15.0, delta_weight: float = 30.0):
        super().__init__()
        self.depth_weight = depth_weight
        self.delta_weight = delta_weight

    def forward(self, pred_delta: torch.Tensor, true_delta: torch.Tensor, current_depth_m: torch.Tensor) -> torch.Tensor:
        depth_factor = torch.tanh(current_depth_m / 0.10)
        delta_factor = torch.tanh(torch.abs(true_delta) / 0.50)
        weights = 1.0 + self.depth_weight * depth_factor + self.delta_weight * delta_factor
        return torch.mean(weights * (pred_delta - true_delta) ** 2)


def get_batched_graph(edge_index: torch.Tensor, edge_weight: torch.Tensor, num_nodes: int, batch_size: int, device: str = "cpu"):
    """
    Precomputes block-diagonal edge_index and edge_weight for batch size B.
    """
    edge_indices = [edge_index.to(device) + i * num_nodes for i in range(batch_size)]
    edge_index_b = torch.cat(edge_indices, dim=1)
    edge_weight_b = edge_weight.to(device).repeat(batch_size)
    return edge_index_b, edge_weight_b


def train_flood_gcn(
    train_ds: FastFloodDataset,
    val_ds: FastFloodDataset,
    model: FloodGCN,
    static_graph: StaticGraph,
    epochs: int = 6,
    lr: float = 0.003,
    batch_size: int = 32,
    use_weighted_loss: bool = True,
    device: str = "cpu",
    checkpoint_path: str = "flood_gcn_checkpoint.pt"
) -> Tuple[list, list]:
    """
    Curriculum multi-step unrolled training loop for FloodGCN.
    """
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    criterion = SeverityWeightedLoss(depth_weight=15.0, delta_weight=30.0) if use_weighted_loss else F.mse_loss

    N = static_graph.num_nodes
    edge_index_b, edge_weight_b = get_batched_graph(
        static_graph.edge_index, static_graph.edge_weight, N, batch_size, device
    )

    # Extract normalization statistics from train_ds (computed strictly across training scenarios)
    norm_mean = train_ds.norm_mean
    norm_std = train_ds.norm_std

    # Save normalization stats to disk alongside checkpoint
    checkpoint_dir = os.path.dirname(checkpoint_path) or "."
    norm_stats_path = os.path.join(checkpoint_dir, "norm_stats.npz")
    np.savez_compressed(
        norm_stats_path,
        mean=norm_mean.cpu().numpy().astype(np.float32),
        std=norm_std.cpu().numpy().astype(np.float32),
        feature_names=NODE_FEATURE_NAMES
    )
    print(f"✅ Saved normalization statistics -> {norm_stats_path}")

    n_train_seq = len(train_ds.seq_indices)
    n_val_seq = len(val_ds.seq_indices)

    train_seq_indices = np.arange(n_train_seq)
    val_seq_indices = np.arange(n_val_seq)

    train_losses = []
    val_losses = []

    norm_mean_dev = norm_mean.to(device)
    norm_std_dev = norm_std.to(device)

    print("\n" + "=" * 70)
    print(f"  TRAINING PLAIN FloodGCN SURROGATE ({epochs} EPOCHS)")
    print(f"  Curriculum:         1-Step (Ep 1-2) -> 3-Step (Ep 3-4) -> 5-Step (Ep 5-6) -> 10-Step (Ep 7-8) -> 15-Step (Ep 9-10)")
    print(f"  Loss Function:      {'Severity-Weighted Loss (15x depth, 30x delta)' if use_weighted_loss else 'Standard MSE'}")
    print(f"  Normalization:      Z-Score Standardization across 8 Features (Training-set only)")
    print(f"  Training Scenarios: {len(train_ds.scenarios)} LHS files ({len(train_ds.indices):,} transitions)")
    print(f"  Validation Scenarios:{len(val_ds.scenarios)} LHS files ({len(val_ds.indices):,} transitions)")
    print(f"  Batch Size:         {batch_size} ({batch_size * N:,} nodes / step)")
    print("=" * 70)

    best_val_loss = float("inf")
    start_time = time.time()
    steps_per_epoch = 150
    val_steps = 40

    for epoch in range(1, epochs + 1):
        if epoch <= 2: unroll_steps = 1
        elif epoch <= 4: unroll_steps = 3
        elif epoch <= 6: unroll_steps = 5
        elif epoch <= 8: unroll_steps = 10
        else: unroll_steps = 15

        model.train()
        np.random.shuffle(train_seq_indices)

        total_train_loss = 0.0
        n_train_batches = 0

        for b_i in range(steps_per_epoch):
            start_idx = b_i * batch_size
            if start_idx + batch_size > n_train_seq:
                break
            b_inds = train_seq_indices[start_idx : start_idx + batch_size]
            batch_data = train_ds.get_sequence_batch(b_inds, unroll_steps=unroll_steps)

            cur_depth = batch_data["depth_0"].to(device)
            elev = batch_data["elev"].to(device)
            bfrac = batch_data["bfrac"].to(device)
            blockage = batch_data["blockage"].to(device)
            area = batch_data["area"].to(device)

            optimizer.zero_grad()
            rollout_loss = torch.tensor(0.0, device=device)
            discount = 1.0

            for k in range(unroll_steps):
                stored_k = batch_data["stored_seq"][k].to(device)
                rain_k = batch_data["rain_seq"][k].to(device)
                cum_rain_k = batch_data["cum_rain_seq"][k].to(device)
                ema_rain_k = batch_data["ema_rain_seq"][k].to(device)
                target_delta_k = batch_data["target_deltas"][k].to(device)

                # Apply log1p transform to heavy-tailed non-negative features
                cur_depth_log = torch.log1p(cur_depth)
                stored_k_log = torch.log1p(stored_k)
                cum_rain_k_log = torch.log1p(cum_rain_k)

                # Assemble 9D raw feature vector:
                # [depth_m (log1p), stored_vol (log1p), rain_rate, elev, bfrac, blockage, area, cum_rain (log1p), ema_rain]
                x_k_raw = torch.cat([
                    cur_depth_log,
                    stored_k_log,
                    rain_k,
                    elev,
                    bfrac,
                    blockage,
                    area,
                    cum_rain_k_log,
                    ema_rain_k
                ], dim=1)

                # Z-score standardization: (x - mean) / (std + eps)
                x_k_norm = (x_k_raw - norm_mean_dev) / (norm_std_dev + 1e-6)

                pred_delta_cm = model(x_k_norm, edge_index_b, edge_weight=edge_weight_b)

                if use_weighted_loss:
                    step_loss = criterion(pred_delta_cm, target_delta_k, cur_depth)
                else:
                    step_loss = F.mse_loss(pred_delta_cm, target_delta_k)

                rollout_loss += discount * step_loss
                discount *= 0.90

                pred_delta_m = pred_delta_cm / 100.0
                cur_depth = torch.clamp(cur_depth + pred_delta_m, min=0.0)

            rollout_loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            total_train_loss += rollout_loss.item() / unroll_steps
            n_train_batches += 1

        scheduler.step()
        avg_train_loss = total_train_loss / max(1, n_train_batches)
        train_losses.append(avg_train_loss)

        model.eval()
        total_val_loss = 0.0
        n_val_batches = 0
        band_errs = {"safe": [], "minor": [], "mod": [], "severe": []}

        with torch.no_grad():
            for v_i in range(val_steps):
                start_idx = v_i * batch_size
                if start_idx + batch_size > len(val_ds.indices): break
                b_inds = list(range(start_idx, start_idx + batch_size))
                x_b, y_b, depth_b = val_ds.get_batch(b_inds)
                x_b, y_b, depth_b = x_b.to(device), y_b.to(device), depth_b.to(device)

                pred_delta = model(x_b, edge_index_b, edge_weight=edge_weight_b)
                if use_weighted_loss:
                    val_loss = criterion(pred_delta, y_b, depth_b)
                else:
                    val_loss = F.mse_loss(pred_delta, y_b)

                total_val_loss += val_loss.item()
                n_val_batches += 1

                diff_sq = (pred_delta - y_b) ** 2
                depths_cm = depth_b * 100.0
                m_safe = depths_cm < 5.0
                m_minor = (depths_cm >= 5.0) & (depths_cm < 15.0)
                m_mod = (depths_cm >= 15.0) & (depths_cm < 30.0)
                m_severe = depths_cm >= 30.0

                if m_safe.any(): band_errs["safe"].append(diff_sq[m_safe].mean().item())
                if m_minor.any(): band_errs["minor"].append(diff_sq[m_minor].mean().item())
                if m_mod.any(): band_errs["mod"].append(diff_sq[m_mod].mean().item())
                if m_severe.any(): band_errs["severe"].append(diff_sq[m_severe].mean().item())

        avg_val_loss = total_val_loss / max(1, n_val_batches)
        val_losses.append(avg_val_loss)

        safe_mse = np.mean(band_errs["safe"]) if band_errs["safe"] else 0.0
        severe_mse = np.mean(band_errs["severe"]) if band_errs["severe"] else 0.0

        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            torch.save(model.state_dict(), checkpoint_path)

        ep_time = time.time() - start_time
        print(f"  Epoch {epoch:02d}/{epochs:02d} (Unroll={unroll_steps}x) │ Train Loss: {avg_train_loss:.6f} │ Val Loss: {avg_val_loss:.6f} "
              f"(Safe MSE: {safe_mse:.5f}, Severe MSE: {severe_mse:.5f}) │ {ep_time:.1f}s", flush=True)

    elapsed = time.time() - start_time
    print(f"\n✅ Training completed in {elapsed:.1f}s! Best Val Loss: {best_val_loss:.6f}")
    return train_losses, val_losses


def evaluate_historical_event(
    model: FloodGCN,
    scenario_npz_path: str,
    static_graph: StaticGraph,
    norm_mean: Optional[torch.Tensor] = None,
    norm_std: Optional[torch.Tensor] = None,
    device: str = "cpu"
) -> dict:
    """
    Performs full closed-loop multi-step autoregressive rollout on a historical storm with 9-feature log1p pipeline.
    """
    if not os.path.exists(scenario_npz_path):
        print(f"Scenario not found: {scenario_npz_path}")
        return None

    if norm_mean is None or norm_std is None:
        norm_stats_path = os.path.join(os.path.dirname(__file__), "norm_stats.npz")
        if os.path.exists(norm_stats_path):
            ns = np.load(norm_stats_path)
            norm_mean = torch.tensor(ns["mean"], dtype=torch.float32)
            norm_std = torch.tensor(ns["std"], dtype=torch.float32)
        else:
            norm_mean = torch.zeros(NUM_NODE_FEATURES, dtype=torch.float32)
            norm_std = torch.ones(NUM_NODE_FEATURES, dtype=torch.float32)

    norm_mean_dev = norm_mean.to(device)
    norm_std_dev = norm_std.to(device)

    npz = np.load(scenario_npz_path)
    sc_id = str(npz["scenario_id"])
    depth_m_true = npz["depth_m"]           # [T, 8001]
    stored_vol = npz["stored_vol_m3"]      # [T, 8001]
    rainfall_rates = npz["rainfall_mm_hr"] # [T]

    T, N = depth_m_true.shape
    edge_index = static_graph.edge_index.to(device)
    edge_weight = static_graph.edge_weight.to(device)
    static_elev = static_graph.elevations.to(device)
    static_bfrac = static_graph.building_fracs.to(device)
    static_area = static_graph.effective_areas.to(device)
    static_blockage = torch.zeros_like(static_elev)

    cur_depth_m = torch.tensor(depth_m_true[0:1].T, dtype=torch.float32).to(device)
    cum_rain_val = torch.zeros_like(cur_depth_m)
    ema_rain_val = torch.full_like(cur_depth_m, fill_value=float(rainfall_rates[0]))

    alpha = 0.033

    predicted_depths_cm = [(cur_depth_m.cpu().numpy() * 100.0)]
    latencies = []
    deltas_step_cm = []

    model.eval()
    model.to(device)

    with torch.no_grad():
        for t in range(T - 1):
            t0 = time.time()
            rain_val = float(rainfall_rates[t])
            stored_t = torch.tensor(stored_vol[t:t+1].T, dtype=torch.float32).to(device)
            rain_t = torch.full_like(cur_depth_m, fill_value=rain_val)
            
            # Update cumulative rain (dt = 30s)
            cum_rain_val += rain_t * (30.0 / 3600.0)
            
            # Update EMA rain (decaying memory)
            if t == 0:
                ema_rain_val = rain_t.clone()
            else:
                ema_rain_val = alpha * rain_t + (1.0 - alpha) * ema_rain_val

            cur_depth_log = torch.log1p(cur_depth_m)
            stored_t_log = torch.log1p(stored_t)
            cum_rain_log = torch.log1p(cum_rain_val)

            x_t_raw = torch.cat([
                cur_depth_log,
                stored_t_log,
                rain_t,
                static_elev,
                static_bfrac,
                static_blockage,
                static_area,
                cum_rain_log,
                ema_rain_val
            ], dim=1)

            x_t_norm = (x_t_raw - norm_mean_dev) / (norm_std_dev + 1e-6)

            pred_delta_cm = model(x_t_norm, edge_index, edge_weight=edge_weight)
            deltas_step_cm.append(pred_delta_cm.cpu().numpy())

            pred_delta_m = pred_delta_cm / 100.0
            next_depth_m = torch.clamp(cur_depth_m + pred_delta_m, min=0.0)

            latencies.append((time.time() - t0) * 1000.0)
            predicted_depths_cm.append(next_depth_m.cpu().numpy() * 100.0)
            cur_depth_m = next_depth_m

    pred_depths_cm = np.array(predicted_depths_cm)
    true_depths_cm = depth_m_true[:, :, np.newaxis] * 100.0
    rmse_cm = float(np.sqrt(np.mean((pred_depths_cm - true_depths_cm) ** 2)))
    peak_true = float(np.max(true_depths_cm))
    peak_pred = float(np.max(pred_depths_cm))

    # Worst node identification
    node_peak_true = np.max(true_depths_cm[:, :, 0], axis=0) # [8001]
    worst_node = int(np.argmax(node_peak_true))
    worst_node_true_peak = float(node_peak_true[worst_node])
    worst_node_pred_peak = float(np.max(pred_depths_cm[:, worst_node, 0]))

    ss_res = np.sum((true_depths_cm - pred_depths_cm) ** 2)
    ss_tot = np.sum((true_depths_cm - np.mean(true_depths_cm)) ** 2)
    r2 = float(1.0 - (ss_res / (ss_tot + 1e-6)))
    avg_latency = float(np.mean(latencies))

    # Receding limb audit (sign check during zero rainfall period)
    deltas_all = np.array(deltas_step_cm) # [T-1, N, 1]
    mid_step = int(len(rainfall_rates) * 0.5)
    mean_delta_rising = float(np.mean(deltas_all[:mid_step]))
    mean_delta_receding = float(np.mean(deltas_all[mid_step:]))

    print("\n" + "=" * 65)
    print(f"  HISTORICAL REPLAY EVALUATION: {sc_id}")
    print("=" * 65)
    print(f"  Duration:                  {T * 0.5:.1f} mins ({T} timesteps)")
    print(f"  Overall RMSE:              {rmse_cm:.2f} cm")
    print(f"  Nash-Sutcliffe R² (NSE):   {r2:.4f}")
    print(f"  Overall Peak Ground Truth: {peak_true:.1f} cm ({peak_true/100:.2f} m)")
    print(f"  Overall Peak GNN Predicted:{peak_pred:.1f} cm ({peak_pred/100:.2f} m)")
    print(f"  Worst Node (Node {worst_node}):")
    print(f"    - Actual Simulator Peak: {worst_node_true_peak:.1f} cm ({worst_node_true_peak/100:.2f} m)")
    print(f"    - FloodGCN Predicted:    {worst_node_pred_peak:.1f} cm ({worst_node_pred_peak/100:.2f} m)")
    print(f"    - Residual Error Gap:    {abs(worst_node_true_peak - worst_node_pred_peak):.1f} cm")
    print(f"  Hydrograph Derivative Sign Audit:")
    print(f"    - Rising Limb Mean Δy:   {mean_delta_rising:+.5f} cm/step")
    print(f"    - Receding Limb Mean Δy: {mean_delta_receding:+.5f} cm/step ({'CORRECT (Negative / Draining)' if mean_delta_receding < 0 else 'INCORRECT (Positive Accumulation)'})")
    print(f"  Inference Latency:         {avg_latency:.2f} ms / step")
    print("=" * 65)

    return {
        "scenario_id": sc_id,
        "true_cm": true_depths_cm,
        "pred_cm": pred_depths_cm,
        "rmse_cm": rmse_cm,
        "r2": r2,
        "peak_true": peak_true,
        "peak_pred": peak_pred,
        "worst_node": worst_node,
        "worst_true": worst_node_true_peak,
        "worst_pred": worst_node_pred_peak,
        "latency_ms": avg_latency,
        "T": T
    }


def render_evaluation_dashboard(eval_results: dict, static_graph: StaticGraph, output_png: str = "flood_gcn_evaluation.png"):
    """
    Renders comparative 4-panel evaluation dashboard.
    """
    true_cm = eval_results["true_cm"]
    pred_cm = eval_results["pred_cm"]
    sc_id = eval_results["scenario_id"]
    T = eval_results["T"]

    peak_idx = int(T * 0.6)
    true_peak = true_cm[peak_idx, :, 0]
    pred_peak = pred_cm[peak_idx, :, 0]

    elevs = static_graph.elevations.numpy()[:, 0]

    fig = plt.figure(figsize=(18, 14), facecolor="#090d16")
    gs = fig.add_gridspec(2, 2, left=0.06, right=0.94, bottom=0.06, top=0.92, wspace=0.15, hspace=0.22)

    # 1. Simulator True Depth Map (Top Left)
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor("#0b0f19")
    sc1 = ax1.scatter(np.arange(len(true_peak)), elevs, c=true_peak, cmap="turbo", vmin=0.0, vmax=50.0, s=8, alpha=0.9)
    ax1.set_title("Simulator (Ground Truth) — Inundation vs Elevation", color="#58a6ff", fontsize=11, fontweight="bold")
    ax1.set_xlabel("Node ID", color="#8b949e", fontsize=9)
    ax1.set_ylabel("Ground Elevation (m)", color="#8b949e", fontsize=9)
    ax1.tick_params(colors="#8b949e", labelsize=8)
    plt.colorbar(sc1, ax=ax1, fraction=0.046, pad=0.04).set_label("Depth (cm)", color="#8b949e", fontsize=8)

    # 2. GNN Predicted Depth Map (Top Right)
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor("#0b0f19")
    sc2 = ax2.scatter(np.arange(len(pred_peak)), elevs, c=pred_peak, cmap="turbo", vmin=0.0, vmax=50.0, s=8, alpha=0.9)
    ax2.set_title("FloodGCN Surrogate — Closed-Loop Rollout Prediction", color="#38bdf8", fontsize=11, fontweight="bold")
    ax2.set_xlabel("Node ID", color="#8b949e", fontsize=9)
    ax2.set_ylabel("Ground Elevation (m)", color="#8b949e", fontsize=9)
    ax2.tick_params(colors="#8b949e", labelsize=8)
    plt.colorbar(sc2, ax=ax2, fraction=0.046, pad=0.04).set_label("Depth (cm)", color="#8b949e", fontsize=8)

    # 3. Dynamic Hydrograph Comparison (Bottom Left)
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.set_facecolor("#0b0f19")
    time_min = np.arange(T) * 0.5
    true_max = np.max(true_cm[:, :, 0], axis=1)
    pred_max = np.max(pred_cm[:, :, 0], axis=1)
    true_mean = np.mean(true_cm[:, :, 0], axis=1) * 10
    pred_mean = np.mean(pred_cm[:, :, 0], axis=1) * 10

    ax3.plot(time_min, true_max, color="#f97316", lw=2.2, label="Simulator Peak Depth (cm)")
    ax3.plot(time_min, pred_max, color="#38bdf8", lw=2.0, linestyle="--", label="FloodGCN Predicted Peak (cm)")
    ax3.plot(time_min, true_mean, color="#22c55e", lw=1.8, label="Simulator Mean Depth (mm)")
    ax3.plot(time_min, pred_mean, color="#a855f7", lw=1.5, linestyle=":", label="FloodGCN Predicted Mean (mm)")
    ax3.set_xlabel("Storm Elapsed Time (minutes)", color="#8b949e", fontsize=9)
    ax3.set_ylabel("Depth", color="#8b949e", fontsize=9)
    ax3.set_title(f"Dynamic Storm Hydrograph ({sc_id})", color="#58a6ff", fontsize=11, fontweight="bold")
    ax3.legend(loc="upper left", facecolor="#111827", edgecolor="#30363d", labelcolor="#f1f5f9", fontsize=8)
    ax3.grid(True, color="#21262d", linestyle=":")
    ax3.tick_params(colors="#8b949e", labelsize=8)

    # 4. Parity Scatter Plot (Bottom Right)
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor("#0b0f19")
    flat_true = true_cm[::3, :, 0].flatten()
    flat_pred = pred_cm[::3, :, 0].flatten()
    ax4.scatter(flat_true, flat_pred, s=2, color="#38bdf8", alpha=0.3, edgecolors="none")
    max_d = max(float(np.max(flat_true)), float(np.max(flat_pred)), 10.0)
    ax4.plot([0, max_d], [0, max_d], color="#ef4444", linestyle="--", lw=1.6, label="Ideal 1:1 Parity")
    ax4.set_xlim(0, max_d * 1.05)
    ax4.set_ylim(0, max_d * 1.05)
    ax4.set_xlabel("Simulator Depth (cm)", color="#8b949e", fontsize=9)
    ax4.set_ylabel("FloodGCN Predicted Depth (cm)", color="#8b949e", fontsize=9)
    ax4.set_title(f"Parity Plot Across All 8,001 Nodes (R² = {eval_results['r2']:.4f})", color="#58a6ff", fontsize=11, fontweight="bold")
    ax4.legend(loc="upper left", facecolor="#111827", edgecolor="#30363d", labelcolor="#f1f5f9", fontsize=8)
    ax4.grid(True, color="#21262d", linestyle=":")
    ax4.tick_params(colors="#8b949e", labelsize=8)

    hud_text = f"  Model: FloodGCN (8.9k params)  │  Event: {sc_id}  │  Worst Node Gap: {abs(eval_results['worst_true'] - eval_results['worst_pred']):.1f} cm  │  Latency: {eval_results['latency_ms']:.2f} ms/step  "
    fig.suptitle("Curriculum Rollout-Trained FloodGCN Validation on Historical Event", color="#ffffff", fontsize=14, fontweight="bold", y=0.97)
    fig.text(0.5, 0.935, hud_text, ha="center", va="center", color="#facc15", fontsize=10, fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.35", facecolor="#111827", edgecolor="#facc15", alpha=0.9))

    fig.savefig(output_png, dpi=180, bbox_inches="tight", facecolor="#090d16")
    plt.close()
    print(f"✅ Exported evaluation plot -> {output_png}")


def main():
    parser = argparse.ArgumentParser(description="Train FloodGCN surrogate")
    parser.add_argument("--epochs", type=int, default=10, help="Number of training epochs")
    parser.add_argument("--lr", type=float, default=0.003, help="Learning rate")
    parser.add_argument("--batch_size", type=int, default=32, help="Batch size")
    parser.add_argument("--weighted", action="store_true", default=True, help="Use severity-weighted loss")
    args = parser.parse_args()

    # 1. Load Dataset Splits (260 LHS: 208 train, 52 val)
    train_ds, val_ds, test_ds = create_scenario_splits(
        scenarios_dir="../data/scenarios",
        static_graph_path="../data/static_graph.npz",
        train_ratio=0.80
    )

    static_graph = StaticGraph("../data/static_graph.npz")

    # 2. Initialize Model
    model = FloodGCN(num_node_features=NUM_NODE_FEATURES, hidden_dim=64, num_layers=3)

    # 3. Train with Curriculum Multi-Step Rollout Loss
    train_losses, val_losses = train_flood_gcn(
        train_ds=train_ds,
        val_ds=val_ds,
        model=model,
        static_graph=static_graph,
        epochs=args.epochs,
        lr=args.lr,
        batch_size=args.batch_size,
        use_weighted_loss=args.weighted,
        checkpoint_path="flood_gcn_checkpoint.pt"
    )

    # 4. Evaluate on Historical Replay Events
    sept2025_file = "../data/scenarios/historical_sept_2025.npz"
    if os.path.exists(sept2025_file):
        eval_res = evaluate_historical_event(model, sept2025_file, static_graph)
        if eval_res:
            render_evaluation_dashboard(eval_res, static_graph, "flood_gcn_sept2025_evaluation.png")

    storm2021_file = "../data/scenarios/historical_2021.npz"
    if os.path.exists(storm2021_file):
        eval_res2 = evaluate_historical_event(model, storm2021_file, static_graph)
        if eval_res2:
            render_evaluation_dashboard(eval_res2, static_graph, "flood_gcn_2021_evaluation.png")


if __name__ == "__main__":
    main()
