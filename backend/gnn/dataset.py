"""
backend/gnn/dataset.py — High-Performance PyTorch Dataset Builder for GNN Surrogate.

Key Features:
  1. Explicit 7-feature node schema shared contract:
       [depth_m, pipe_stored_vol_m3, rainfall_rate_mm_hr, elevation_m, building_fraction, blockage_pct, catchment_area_m2]
  2. In-Memory Vectorized Scenario Trajectories:
       O(1) slicing for both single-step transitions and multi-step unrolled sequences.
  3. Scenario-Level Train/Val/Test Splitting:
       - 260 Synthetic LHS scenarios split 80% train (208 files) / 20% val (52 files).
       - Historical replay scenarios (Sept 2025, 2021) are strictly held out in test.
"""

import os
import glob
from typing import Dict, List, Optional, Tuple
import numpy as np
import torch
from torch.utils.data import Dataset

from model import NUM_NODE_FEATURES, NODE_FEATURE_NAMES


class StaticGraph:
    """
    Loads and holds the invariant 8,001-node, 14,344-edge drainage graph.
    """
    def __init__(self, static_graph_path: str = "../data/static_graph.npz"):
        if not os.path.exists(static_graph_path):
            raise FileNotFoundError(f"Static graph not found at: {static_graph_path}. Run run_batch.py first!")

        data = np.load(static_graph_path)
        self.edge_index = torch.tensor(data["edge_index"], dtype=torch.long) # [2, E]
        self.edge_weight = torch.tensor(data["edge_weight"], dtype=torch.float32) # [E]
        self.elevations = torch.tensor(data["elevations"], dtype=torch.float32).unsqueeze(1) # [N, 1]
        self.building_fracs = torch.tensor(data["building_fracs"], dtype=torch.float32).unsqueeze(1) # [N, 1]
        self.effective_areas = torch.tensor(data["effective_areas"], dtype=torch.float32).unsqueeze(1) # [N, 1]
        self.host_cells = data["host_cells"]
        self.num_nodes = int(data["num_nodes"])
        self.num_edges = int(data["num_edges"])


def compute_ema_rain(rainfall: torch.Tensor, alpha: float = 0.033) -> torch.Tensor:
    """
    Computes exponential moving average of rainfall rate:
        ema[t] = alpha * rain[t] + (1 - alpha) * ema[t-1]
    With alpha = 0.033 and dt = 30s, the EMA decays to <10% (0.095) in 35 minutes
    (70 steps: (1 - 0.033)^70 = 0.0954) after rainfall stops.
    """
    ema = torch.zeros_like(rainfall)
    if len(rainfall) > 0:
        ema[0] = rainfall[0]
        for t in range(1, len(rainfall)):
            ema[t] = alpha * rainfall[t] + (1.0 - alpha) * ema[t - 1]
    return ema


class FastFloodDataset(Dataset):
    """
    High-Performance in-memory Dataset holding scenario trajectories with log1p transformation & z-score standardization.
    """
    def __init__(
        self,
        scenario_files: List[str],
        static_graph: StaticGraph,
        scale_delta_cm: bool = True,
        norm_mean: Optional[torch.Tensor] = None,
        norm_std: Optional[torch.Tensor] = None,
    ):
        self.static_graph = static_graph
        self.scale_delta_cm = scale_delta_cm

        # Invariant static node attributes: [elev, bfrac, blockage, area]
        self.static_elev = static_graph.elevations       # [N, 1]
        self.static_bfrac = static_graph.building_fracs   # [N, 1]
        self.static_area = static_graph.effective_areas   # [N, 1]
        self.static_blockage = torch.zeros_like(self.static_elev)

        self.scenarios = []
        self.indices = []          # (sc_idx, t) for single-step
        self.seq_indices = []      # (sc_idx, t) where t + 15 < T for multi-step
        self._load_scenarios(scenario_files)

        # ── Compute or assign z-score normalization statistics ──
        if norm_mean is not None and norm_std is not None:
            self.norm_mean = norm_mean.clone().detach().to(torch.float32)
            self.norm_std = norm_std.clone().detach().to(torch.float32)
        else:
            self.norm_mean, self.norm_std = self._compute_normalization_stats()

    def _compute_normalization_stats(self) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Computes exact mean and std for all 9 input features across this dataset's scenarios
        with log1p applied to heavy-tailed non-negative features (depth_m, stored_vol, cum_rain).
        """
        if len(self.scenarios) == 0:
            return torch.zeros(9, dtype=torch.float32), torch.ones(9, dtype=torch.float32)

        print(f"Computing log1p + z-score normalization statistics across {len(self.scenarios)} scenarios...")
        all_depths = []
        all_stored = []
        all_rain = []
        all_cum_rain = []
        all_ema_rain = []

        N = self.static_graph.num_nodes

        for sc in self.scenarios:
            all_depths.append(sc["depth_m"].flatten())
            all_stored.append(sc["stored_vol"].flatten())
            all_rain.append(torch.repeat_interleave(sc["rainfall"], N))
            all_cum_rain.append(torch.repeat_interleave(sc["cum_rain"], N))
            all_ema_rain.append(torch.repeat_interleave(sc["ema_rain"], N))

        d_all = torch.cat(all_depths)
        s_all = torch.cat(all_stored)
        r_all = torch.cat(all_rain)
        cr_all = torch.cat(all_cum_rain)
        ema_all = torch.cat(all_ema_rain)

        total_obs = len(d_all)
        num_timesteps = total_obs // N

        elev_all = self.static_elev.repeat(num_timesteps, 1).flatten()
        bfrac_all = self.static_bfrac.repeat(num_timesteps, 1).flatten()
        blockage_all = self.static_blockage.repeat(num_timesteps, 1).flatten()
        area_all = self.static_area.repeat(num_timesteps, 1).flatten()

        # Apply log1p transform to heavy-tailed non-negative features
        d_all_log = torch.log1p(d_all)
        s_all_log = torch.log1p(s_all)
        cr_all_log = torch.log1p(cr_all)

        raw_features = torch.stack([
            d_all_log, s_all_log, r_all, elev_all, bfrac_all, blockage_all, area_all, cr_all_log, ema_all
        ], dim=1) # [total_obs, 9]

        mean = torch.mean(raw_features, dim=0) # [9]
        std = torch.std(raw_features, dim=0)   # [9]

        # Prevent divide-by-zero on constant features (e.g. blockage_pct)
        std = torch.where(std < 1e-6, torch.ones_like(std), std)

        print(f"  Normalization stats computed (9 features):")
        for i, fn in enumerate(NODE_FEATURE_NAMES):
            print(f"    - [{i}] {fn:<22}: mean = {mean[i].item():10.4f}, std = {std[i].item():10.4f}")

        return mean, std

    def _load_scenarios(self, scenario_files: List[str]):
        print(f"Loading {len(scenario_files)} scenario files into FastFloodDataset...")
        for fpath in scenario_files:
            if not os.path.exists(fpath):
                continue
            npz = np.load(fpath)
            sc_id = str(npz["scenario_id"])
            source = str(npz["source"])
            depth_m = torch.tensor(npz["depth_m"], dtype=torch.float32)           # [T, N]
            stored_vol = torch.tensor(npz["stored_vol_m3"], dtype=torch.float32)  # [T, N]
            rainfall = torch.tensor(npz["rainfall_mm_hr"], dtype=torch.float32)   # [T]
            cum_rain = torch.cumsum(rainfall * (30.0 / 3600.0), dim=0)            # [T]
            ema_rain = compute_ema_rain(rainfall, alpha=0.033)                    # [T]

            sc_idx = len(self.scenarios)
            self.scenarios.append({
                "scenario_id": sc_id,
                "source": source,
                "depth_m": depth_m,
                "stored_vol": stored_vol,
                "rainfall": rainfall,
                "cum_rain": cum_rain,
                "ema_rain": ema_rain,
            })

            T, N = depth_m.shape
            for t in range(T - 1):
                self.indices.append((sc_idx, t))
                if t + 15 < T:
                    self.seq_indices.append((sc_idx, t))

        print(f"  Loaded {len(self.scenarios)} scenarios -> {len(self.indices):,} transition pairs ({len(self.indices) * self.static_graph.num_nodes:,} node-transitions).")

    def __len__(self) -> int:
        return len(self.indices)

    def get_batch(self, batch_indices: List[int]) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Extracts a single-step vectorized batch of shape [B * N, 9] with log1p and z-score standardization.
        """
        B = len(batch_indices)
        N = self.static_graph.num_nodes

        depth_t_list = []
        depth_next_list = []
        stored_t_list = []
        rain_t_list = []
        cum_rain_list = []
        ema_rain_list = []

        for idx in batch_indices:
            sc_idx, t = self.indices[idx]
            sc = self.scenarios[sc_idx]
            depth_t_list.append(sc["depth_m"][t])
            depth_next_list.append(sc["depth_m"][t + 1])
            stored_t_list.append(sc["stored_vol"][t])
            rain_t_list.append(sc["rainfall"][t].item())
            cum_rain_list.append(sc["cum_rain"][t].item())
            ema_rain_list.append(sc["ema_rain"][t].item())

        depth_t = torch.stack(depth_t_list, dim=0)
        depth_next = torch.stack(depth_next_list, dim=0)
        stored_t = torch.stack(stored_t_list, dim=0)
        rain_t = torch.tensor(rain_t_list, dtype=torch.float32).unsqueeze(1).expand(B, N)
        cum_rain_t = torch.tensor(cum_rain_list, dtype=torch.float32).unsqueeze(1).expand(B, N)
        ema_rain_t = torch.tensor(ema_rain_list, dtype=torch.float32).unsqueeze(1).expand(B, N)

        depth_t_flat = depth_t.reshape(B * N, 1)
        depth_next_flat = depth_next.reshape(B * N, 1)
        stored_t_flat = stored_t.reshape(B * N, 1)
        rain_t_flat = rain_t.reshape(B * N, 1)
        cum_rain_flat = cum_rain_t.reshape(B * N, 1)
        ema_rain_flat = ema_rain_t.reshape(B * N, 1)

        elev_flat = self.static_elev.repeat(B, 1)
        bfrac_flat = self.static_bfrac.repeat(B, 1)
        blockage_flat = self.static_blockage.repeat(B, 1)
        area_flat = self.static_area.repeat(B, 1)

        # Apply log1p transform to heavy-tailed non-negative features
        depth_t_log = torch.log1p(depth_t_flat)
        stored_t_log = torch.log1p(stored_t_flat)
        cum_rain_log = torch.log1p(cum_rain_flat)

        x_raw = torch.cat([
            depth_t_log,
            stored_t_log,
            rain_t_flat,
            elev_flat,
            bfrac_flat,
            blockage_flat,
            area_flat,
            cum_rain_log,
            ema_rain_flat
        ], dim=1) # [B * N, 9]

        # Apply z-score standardization: (x - mean) / (std + eps)
        x_norm = (x_raw - self.norm_mean) / (self.norm_std + 1e-6)

        delta_y = (depth_next_flat - depth_t_flat) * 100.0 if self.scale_delta_cm else (depth_next_flat - depth_t_flat)
        return x_norm, delta_y, depth_t_flat

    def get_sequence_batch(self, batch_seq_indices: List[int], unroll_steps: int = 4) -> Dict[str, torch.Tensor]:
        """
        Extracts a sequence batch for multi-step autoregressive rollout training with 9 features.
        """
        B = len(batch_seq_indices)
        N = self.static_graph.num_nodes
        K = unroll_steps

        init_depths = []
        stored_seq = [[] for _ in range(K)]
        rain_seq = [[] for _ in range(K)]
        cum_rain_seq = [[] for _ in range(K)]
        ema_rain_seq = [[] for _ in range(K)]
        target_deltas = [[] for _ in range(K)]

        for idx in batch_seq_indices:
            sc_idx, t = self.seq_indices[idx]
            sc = self.scenarios[sc_idx]

            init_depths.append(sc["depth_m"][t]) # [N]

            for k in range(K):
                stored_seq[k].append(sc["stored_vol"][t + k])
                rain_seq[k].append(sc["rainfall"][t + k].item())
                cum_rain_seq[k].append(sc["cum_rain"][t + k].item())
                ema_rain_seq[k].append(sc["ema_rain"][t + k].item())

                d_cur = sc["depth_m"][t + k]
                d_next = sc["depth_m"][t + k + 1]
                target_deltas[k].append((d_next - d_cur) * 100.0 if self.scale_delta_cm else (d_next - d_cur))

        # Initial depth: [B * N, 1]
        depth_0 = torch.stack(init_depths, dim=0).reshape(B * N, 1)

        stored_tensors = [torch.stack(stored_seq[k], dim=0).reshape(B * N, 1) for k in range(K)]
        rain_tensors = [torch.tensor(rain_seq[k], dtype=torch.float32).unsqueeze(1).expand(B, N).reshape(B * N, 1) for k in range(K)]
        cum_rain_tensors = [torch.tensor(cum_rain_seq[k], dtype=torch.float32).unsqueeze(1).expand(B, N).reshape(B * N, 1) for k in range(K)]
        ema_rain_tensors = [torch.tensor(ema_rain_seq[k], dtype=torch.float32).unsqueeze(1).expand(B, N).reshape(B * N, 1) for k in range(K)]
        delta_tensors = [torch.stack(target_deltas[k], dim=0).reshape(B * N, 1) for k in range(K)]

        elev_flat = self.static_elev.repeat(B, 1)
        bfrac_flat = self.static_bfrac.repeat(B, 1)
        blockage_flat = self.static_blockage.repeat(B, 1)
        area_flat = self.static_area.repeat(B, 1)

        return {
            "depth_0": depth_0,
            "stored_seq": stored_tensors,
            "rain_seq": rain_tensors,
            "cum_rain_seq": cum_rain_tensors,
            "ema_rain_seq": ema_rain_tensors,
            "target_deltas": delta_tensors,
            "elev": elev_flat,
            "bfrac": bfrac_flat,
            "blockage": blockage_flat,
            "area": area_flat,
            "norm_mean": self.norm_mean,
            "norm_std": self.norm_std,
            "B": B,
            "K": K
        }


def create_scenario_splits(
    scenarios_dir: str = "../data/scenarios",
    static_graph_path: str = "../data/static_graph.npz",
    train_ratio: float = 0.80,
    seed: int = 42,
) -> Tuple[FastFloodDataset, FastFloodDataset, FastFloodDataset]:
    """
    Creates train/val/test datasets with strict SCENARIO-LEVEL splitting.
    Historical replay scenarios are routed strictly to test/val.
    """
    static_graph = StaticGraph(static_graph_path)

    all_files = sorted(glob.glob(os.path.join(scenarios_dir, "*.npz")))
    if not all_files:
        raise FileNotFoundError(f"No .npz scenario files found in {scenarios_dir}!")

    lhs_files = [f for f in all_files if "lhs_" in os.path.basename(f)]
    hist_files = [f for f in all_files if "historical_" in os.path.basename(f)]

    rng = np.random.default_rng(seed)
    n_lhs = len(lhs_files)
    perm = rng.permutation(n_lhs)

    n_train = int(n_lhs * train_ratio)
    train_indices = perm[:n_train]
    val_indices = perm[n_train:]

    train_files = [lhs_files[i] for i in train_indices]
    val_files = [lhs_files[i] for i in val_indices]
    test_files = hist_files

    print("\n" + "=" * 65)
    print("  SCENARIO-LEVEL DATASET SPLIT (260 LHS + 2 HISTORICAL)")
    print("=" * 65)
    print(f"  Training Scenarios (Synthetic LHS only): {len(train_files):2d} files (80%)")
    print(f"  Validation Scenarios (Synthetic LHS):    {len(val_files):2d} files (20%)")
    print(f"  Testing Scenarios (Historical Replays):  {len(test_files):2d} files ({[os.path.basename(f) for f in test_files]})")
    print("=" * 65)

    train_ds = FastFloodDataset(train_files, static_graph, scale_delta_cm=True)
    val_ds = FastFloodDataset(val_files, static_graph, scale_delta_cm=True, norm_mean=train_ds.norm_mean, norm_std=train_ds.norm_std)
    test_ds = FastFloodDataset(test_files, static_graph, scale_delta_cm=True, norm_mean=train_ds.norm_mean, norm_std=train_ds.norm_std) if test_files else None

    return train_ds, val_ds, test_ds
