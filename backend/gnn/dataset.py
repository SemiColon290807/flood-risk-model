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


class FastFloodDataset(Dataset):
    """
    High-Performance in-memory Dataset holding scenario trajectories.
    """
    def __init__(
        self,
        scenario_files: List[str],
        static_graph: StaticGraph,
        scale_delta_cm: bool = True,
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
        self.seq_indices = []      # (sc_idx, t) where t + 5 < T for multi-step
        self._load_scenarios(scenario_files)

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

            sc_idx = len(self.scenarios)
            self.scenarios.append({
                "scenario_id": sc_id,
                "source": source,
                "depth_m": depth_m,
                "stored_vol": stored_vol,
                "rainfall": rainfall,
                "cum_rain": cum_rain,
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
        Extracts a single-step vectorized batch of shape [B * N, 7] and targets [B * N, 1].
        """
        B = len(batch_indices)
        N = self.static_graph.num_nodes

        depth_t_list = []
        depth_next_list = []
        stored_t_list = []
        rain_t_list = []
        cum_rain_list = []

        for idx in batch_indices:
            sc_idx, t = self.indices[idx]
            sc = self.scenarios[sc_idx]
            depth_t_list.append(sc["depth_m"][t])
            depth_next_list.append(sc["depth_m"][t + 1])
            stored_t_list.append(sc["stored_vol"][t])
            rain_t_list.append(sc["rainfall"][t].item())
            cum_rain_list.append(sc["cum_rain"][t].item())

        depth_t = torch.stack(depth_t_list, dim=0)
        depth_next = torch.stack(depth_next_list, dim=0)
        stored_t = torch.stack(stored_t_list, dim=0)
        rain_t = torch.tensor(rain_t_list, dtype=torch.float32).unsqueeze(1).expand(B, N)
        cum_rain_t = torch.tensor(cum_rain_list, dtype=torch.float32).unsqueeze(1).expand(B, N)

        depth_t_flat = depth_t.reshape(B * N, 1)
        depth_next_flat = depth_next.reshape(B * N, 1)
        stored_t_flat = stored_t.reshape(B * N, 1)
        rain_t_flat = rain_t.reshape(B * N, 1)
        cum_rain_flat = cum_rain_t.reshape(B * N, 1)

        elev_flat = self.static_elev.repeat(B, 1)
        bfrac_flat = self.static_bfrac.repeat(B, 1)
        blockage_flat = self.static_blockage.repeat(B, 1)
        area_flat = self.static_area.repeat(B, 1)

        x = torch.cat([
            depth_t_flat,
            stored_t_flat,
            rain_t_flat,
            elev_flat,
            bfrac_flat,
            blockage_flat,
            area_flat,
            cum_rain_flat
        ], dim=1) # [B * N, 8]

        delta_y = (depth_next_flat - depth_t_flat) * 100.0 if self.scale_delta_cm else (depth_next_flat - depth_t_flat)
        return x, delta_y, depth_t_flat

    def get_sequence_batch(self, batch_seq_indices: List[int], unroll_steps: int = 4) -> Dict[str, torch.Tensor]:
        """
        Extracts a sequence batch for multi-step autoregressive rollout training.
        """
        B = len(batch_seq_indices)
        N = self.static_graph.num_nodes
        K = unroll_steps

        init_depths = []
        stored_seq = [[] for _ in range(K)]
        rain_seq = [[] for _ in range(K)]
        cum_rain_seq = [[] for _ in range(K)]
        target_deltas = [[] for _ in range(K)]

        for idx in batch_seq_indices:
            sc_idx, t = self.seq_indices[idx]
            sc = self.scenarios[sc_idx]

            init_depths.append(sc["depth_m"][t]) # [N]

            for k in range(K):
                stored_seq[k].append(sc["stored_vol"][t + k])
                rain_seq[k].append(sc["rainfall"][t + k].item())
                cum_rain_seq[k].append(sc["cum_rain"][t + k].item())

                d_cur = sc["depth_m"][t + k]
                d_next = sc["depth_m"][t + k + 1]
                target_deltas[k].append((d_next - d_cur) * 100.0 if self.scale_delta_cm else (d_next - d_cur))

        # Initial depth: [B * N, 1]
        depth_0 = torch.stack(init_depths, dim=0).reshape(B * N, 1)

        stored_tensors = [torch.stack(stored_seq[k], dim=0).reshape(B * N, 1) for k in range(K)]
        rain_tensors = [torch.tensor(rain_seq[k], dtype=torch.float32).unsqueeze(1).expand(B, N).reshape(B * N, 1) for k in range(K)]
        cum_rain_tensors = [torch.tensor(cum_rain_seq[k], dtype=torch.float32).unsqueeze(1).expand(B, N).reshape(B * N, 1) for k in range(K)]
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
            "target_deltas": delta_tensors,
            "elev": elev_flat,
            "bfrac": bfrac_flat,
            "blockage": blockage_flat,
            "area": area_flat,
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
    val_ds = FastFloodDataset(val_files, static_graph, scale_delta_cm=True)
    test_ds = FastFloodDataset(test_files, static_graph, scale_delta_cm=True) if test_files else None

    return train_ds, val_ds, test_ds
