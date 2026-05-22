"""GATv2 implemented from scratch (no PyTorch Geometric dependency).

Concept taught: graph attention. Each node's representation is updated
by attending over its neighbours' features. GATv2 fixes the
expressiveness limitation of GAT (Brody, Alon, Yahav 2022) by moving
the attention head's nonlinearity earlier:

    e_ij = a^T LeakyReLU(W [h_i || h_j])    (GAT, original)
    e_ij = a^T LeakyReLU(W_1 h_i + W_2 h_j) (GATv2)

The latter is strictly more expressive — GAT (v1) cannot represent
"max" over neighbours; GATv2 can. We use it because the Penumbra
pathfinder's whole job is "pick the neighbour with the shortest
remaining path" — exactly a max-style query.

Pedagogical implementation: dense adjacency (since our arena is
<200 nodes the dense version is faster than sparse on MPS and
inspectable line-by-line). Production scale-out would use PyG.

References
- Brody, Alon, Yahav. "How attentive are graph attention networks?"
  (ICLR 2022).
- Veličković et al., "Graph attention networks" (ICLR 2018). The
  original GAT.
"""

from __future__ import annotations

import torch
from torch import Tensor, nn


class GATv2Layer(nn.Module):
    """One GATv2 attention layer.

    Inputs
    - x: (n_nodes, in_dim)
    - adj: (n_nodes, n_nodes) boolean — A_ij ⇔ edge i↔j; include self-loops.
    - edge_cost: (n_nodes, n_nodes) float — augments attention with the
      edge weight so the layer can prefer cheap neighbours.

    Output
    - (n_nodes, out_dim)
    """

    def __init__(self, in_dim: int, out_dim: int, *, leaky_slope: float = 0.2) -> None:
        super().__init__()
        self.w_left = nn.Linear(in_dim, out_dim, bias=False)
        self.w_right = nn.Linear(in_dim, out_dim, bias=False)
        self.attn = nn.Linear(out_dim, 1, bias=False)
        self.activation = nn.LeakyReLU(negative_slope=leaky_slope)
        self.cost_weight = nn.Parameter(torch.zeros(1))  # learnable scalar

    def forward(self, x: Tensor, adj: Tensor, edge_cost: Tensor) -> Tensor:
        out, _ = self.forward_with_attention(x, adj, edge_cost)
        return out

    def forward_with_attention(
        self, x: Tensor, adj: Tensor, edge_cost: Tensor
    ) -> tuple[Tensor, Tensor]:
        """Same as `forward` but also returns the (n, n) attention matrix."""
        wl = self.w_left(x)
        wr = self.w_right(x)
        e_per_edge = self.activation(wl.unsqueeze(1) + wr.unsqueeze(0))
        scores = self.attn(e_per_edge).squeeze(-1)
        scores = scores + self.cost_weight * edge_cost
        scores = scores.masked_fill(~adj, float("-inf"))
        attention = torch.softmax(scores, dim=-1)
        return attention @ wr, attention


class GATv2Pathfinder(nn.Module):
    """Two-layer GATv2 estimator: node + adj + costs → per-node value.

    Output is interpreted as the negative estimated distance to the
    nearest goal — higher = "better to be here". The actor in MAPPO
    sees this as a per-neighbour feature.
    """

    def __init__(self, *, in_dim: int = 2, hidden_dim: int = 32, out_dim: int = 1) -> None:
        super().__init__()
        self.layer1 = GATv2Layer(in_dim, hidden_dim)
        self.layer2 = GATv2Layer(hidden_dim, hidden_dim)
        self.readout = nn.Linear(hidden_dim, out_dim)

    def forward(self, x: Tensor, adj: Tensor, edge_cost: Tensor) -> Tensor:
        h = torch.relu(self.layer1(x, adj, edge_cost))
        h = torch.relu(self.layer2(h, adj, edge_cost))
        return self.readout(h).squeeze(-1)

    def attention_matrices(
        self, x: Tensor, adj: Tensor, edge_cost: Tensor
    ) -> tuple[Tensor, Tensor, Tensor]:
        """Run the network and return (value, attention_layer1, attention_layer2).

        Inspection path used by the dashboard. The attention matrix from
        layer 1 shows which neighbours each node attends to in the first
        hop; the layer-2 matrix shows the second-hop attention.
        """
        h1, attn1 = self.layer1.forward_with_attention(x, adj, edge_cost)
        h1_relu = torch.relu(h1)
        h2, attn2 = self.layer2.forward_with_attention(h1_relu, adj, edge_cost)
        h2_relu = torch.relu(h2)
        return self.readout(h2_relu).squeeze(-1), attn1, attn2
