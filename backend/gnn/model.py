"""
backend/gnn/model.py

GNN surrogate architecture for the flood nowcasting simulator.

Task framing (see PROJECT_CONTEXT.md Section 3.4, 13, and design discussion):
    - One-step transition prediction: given the graph state at time t,
      predict the CHANGE in standing water depth at t+1 for every node.
    - Node features (x): current depth, current pipe stored volume/flow,
      current rainfall rate, elevation, building_fraction, blockage_pct,
      catchment_area.
    - Edge structure (edge_index): the fixed 14,344-edge drainage graph,
      identical across every scenario/timestep.
    - Edge weight: a single scalar per edge (effective, blockage-adjusted
      pipe capacity) fed to GCNConv's edge_weight argument. We deliberately
      do NOT use a multi-dimensional edge_attr layer (e.g. NNConv/GINEConv)
      yet -- per the project roadmap, start with a plain GCN and only add
      that complexity if the simple version demonstrably underfits.
    - Target (y): depth delta, NOT absolute depth. Residual targets are
      easier to learn for physical simulations since the network mostly
      needs to output ~0 and only "correct" where something is changing.

This file defines the architecture and self-test verification.
"""

from typing import List, Optional
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GCNConv

# Explicit shared schema contract for node features (9 features)
NODE_FEATURE_NAMES: List[str] = [
    "depth_m",              # [0] Current standing water depth on host cell (m) [log1p transformed]
    "pipe_stored_vol_m3",   # [1] Current surcharged overflow / stored volume (m³) [log1p transformed]
    "rainfall_rate_mm_hr",  # [2] Instantaneous rainfall intensity (mm/hr)
    "elevation_m",          # [3] Ground DEM elevation at junction (m)
    "building_fraction",    # [4] Host cell building fraction / imperviousness [0, 1]
    "blockage_pct",         # [5] Pipe blockage percentage [0, 1]
    "catchment_area_m2",    # [6] Host cell effective open catchment area (m²)
    "cum_rain_mm",          # [7] Cumulative storm rainfall depth so far (mm) [log1p transformed]
    "ema_rain_mm_hr",       # [8] Exponential moving average of rain intensity (decaying memory) (mm/hr)
]
NUM_NODE_FEATURES: int = len(NODE_FEATURE_NAMES)


class FloodGCN(nn.Module):
    """
    Plain stacked-GCNConv surrogate model with bounded output head.

    Architecture:
        input (9 features)
          -> GCNConv -> ReLU -> Dropout   (repeated num_layers - 1 times)
          -> GCNConv -> (no activation)   (final layer, projects to hidden_dim)
          -> Linear -> max_delta_cm * tanh(x)  (bounded regression head: +/- max_delta_cm per step)
    """

    def __init__(
        self,
        num_node_features: int = NUM_NODE_FEATURES,
        hidden_dim: int = 64,
        num_layers: int = 3,
        dropout: float = 0.1,
        max_delta_cm: float = 25.0,
    ):
        super().__init__()

        if num_layers < 2:
            raise ValueError("num_layers must be >= 2 (need at least one hidden GCN layer)")

        self.dropout = dropout
        self.max_delta_cm = max_delta_cm

        self.convs = nn.ModuleList()
        self.convs.append(GCNConv(num_node_features, hidden_dim))
        for _ in range(num_layers - 1):
            self.convs.append(GCNConv(hidden_dim, hidden_dim))

        # Bounded regression head: hidden representation -> scalar depth delta per node
        self.output_head = nn.Linear(hidden_dim, 1)

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_weight: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Args:
            x:            [num_nodes, num_node_features] node feature matrix
            edge_index:   [2, num_edges] graph connectivity (COO format)
            edge_weight:  [num_edges] optional scalar per edge
                          (e.g. effective, blockage-adjusted pipe capacity)

        Returns:
            [num_nodes, 1] predicted depth delta per node bounded in [-max_delta_cm, +max_delta_cm]
        """
        h = x
        for i, conv in enumerate(self.convs):
            h = conv(h, edge_index, edge_weight=edge_weight)
            is_last = i == len(self.convs) - 1
            if not is_last:
                h = F.relu(h)
                h = F.dropout(h, p=self.dropout, training=self.training)

        raw_delta = self.output_head(h)
        depth_delta = self.max_delta_cm * torch.tanh(raw_delta)
        return depth_delta


# ---------------------------------------------------------------------------
# Self-test: verify the architecture runs on dummy data shaped like the
# real JU drainage graph (8,001 nodes, 14,344 edges), before dataset.py
# or any real simulator output exists.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    torch.manual_seed(0)

    NUM_NODES = 8_001
    NUM_EDGES = 14_344

    print(f"Building dummy graph: {NUM_NODES} nodes, {NUM_EDGES} edges, "
          f"{NUM_NODE_FEATURES} node features ({NODE_FEATURE_NAMES})")

    x = torch.randn(NUM_NODES, NUM_NODE_FEATURES)

    # Random directed edges (valid node index pairs)
    edge_index = torch.randint(0, NUM_NODES, (2, NUM_EDGES), dtype=torch.long)

    # Scalar edge weight stand-in for effective pipe capacity
    edge_weight = torch.rand(NUM_EDGES) * 2.0  # arbitrary positive range

    model = FloodGCN(num_node_features=NUM_NODE_FEATURES, hidden_dim=64, num_layers=3)
    print(model)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"\nTotal trainable parameters: {total_params:,}")

    # --- Forward pass shape check ---
    model.train()
    pred = model(x, edge_index, edge_weight=edge_weight)
    print(f"\nForward pass output shape: {tuple(pred.shape)} "
          f"(expected ({NUM_NODES}, 1))")
    assert pred.shape == (NUM_NODES, 1), "Output shape mismatch!"

    # --- Backward pass check: make sure gradients actually flow ---
    dummy_target = torch.randn(NUM_NODES, 1) * 0.01  # small deltas, like real targets
    loss = F.mse_loss(pred, dummy_target)
    loss.backward()

    grad_norms = [p.grad.norm().item() for p in model.parameters() if p.grad is not None]
    print(f"\nDummy MSE loss: {loss.item():.6f}")
    print(f"Number of parameter tensors with gradients: {len(grad_norms)} "
          f"(expected {total_params and len(list(model.parameters()))})")
    print(f"Mean gradient norm across parameters: "
          f"{sum(grad_norms) / len(grad_norms):.6f}")

    assert all(g == g for g in grad_norms), "NaN detected in gradients!"
    print("\nAll checks passed: forward pass shape correct, "
          "backward pass produces finite gradients.")
