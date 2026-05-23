"""GNN encoder over the supply graph for logistics-aware policies.

Concept taught: how a graph neural network compresses the structural
context an RL policy needs to dispatch carriers — neighbour
inventory, edge costs, demand pressure — into a fixed-size
embedding that can be concatenated to the per-agent observation.

Implementation note: this module uses the canonical
`torch_geometric.nn.GATv2Conv` (PyG) graph attention layer with the
GATv2 expressiveness fix. PyG expects sparse `(x, edge_index)`
inputs — we convert the dense `adj` + `edge_cost` arguments the
arena hands us into that format inside `forward`. Edge weights are
fed through `edge_dim=1` so the attention coefficients can attend
over them. The in-tree `GATv2Layer` in `gat_pathfinder.py` is kept
intact for the original pathfinder use case.

Output is a hidden_dim-sized vector keyed by the agent's current
node — i.e. the policy sees a contextual embedding of the supply
network from the agent's perspective.

Spec: LOGISTICS_PLAN.md Tier 4 at repo root.
"""

from __future__ import annotations

import torch
from torch import Tensor, nn
from torch_geometric.nn import GATv2Conv

DEFAULT_HIDDEN_DIM: int = 16


def _dense_to_edge_index(adj: Tensor, edge_cost: Tensor) -> tuple[Tensor, Tensor]:
    """Convert a dense boolean adjacency + cost matrix to PyG sparse form.

    Returns `(edge_index, edge_attr)` where `edge_index` has shape
    `[2, num_edges]` and `edge_attr` has shape `[num_edges, 1]`.
    """
    if adj.dim() != 2 or adj.size(0) != adj.size(1):
        raise ValueError(f"adj must be a square 2-D tensor; got shape {tuple(adj.shape)}")
    if edge_cost.shape != adj.shape:
        raise ValueError(
            f"edge_cost shape {tuple(edge_cost.shape)} must match adj shape {tuple(adj.shape)}"
        )
    src, dst = adj.nonzero(as_tuple=True)
    edge_index = torch.stack([src, dst], dim=0).to(torch.long)
    edge_attr = edge_cost[src, dst].to(torch.float32).unsqueeze(-1)
    return edge_index, edge_attr


class SupplyGraphEncoder(nn.Module):
    """Two-layer GATv2 encoder over a supply graph snapshot.

    Inputs
    - node_features: (n_nodes, in_dim) — per-node features (e.g.
      `[inventory_ratio, demand_rate, treasury_norm]`).
    - adj: (n_nodes, n_nodes) bool — adjacency with self-loops.
    - edge_cost: (n_nodes, n_nodes) float — edge weights from arena.
    - agent_position: int (node index where the agent sits).

    Output
    - (hidden_dim,) — the embedding of the agent's node after two
      hops of graph attention.

    The encoder is intentionally tiny (hidden_dim=16 by default) so
    its parameter count stays well inside the M4 memory budget when
    instantiated per env.
    """

    def __init__(
        self,
        *,
        in_dim: int = 3,
        hidden_dim: int = DEFAULT_HIDDEN_DIM,
    ) -> None:
        super().__init__()
        if hidden_dim < 8 or hidden_dim > 64:
            raise ValueError(
                f"hidden_dim must be in [8, 64] to respect the memory budget; got {hidden_dim}"
            )
        self.in_dim = in_dim
        self.hidden_dim = hidden_dim
        # add_self_loops=False: the arena's adjacency already encodes self-loops,
        # and PyG would otherwise complain when edge_attr is provided.
        self.layer1 = GATv2Conv(
            in_channels=in_dim,
            out_channels=hidden_dim,
            heads=1,
            concat=False,
            edge_dim=1,
            add_self_loops=False,
        )
        self.layer2 = GATv2Conv(
            in_channels=hidden_dim,
            out_channels=hidden_dim,
            heads=1,
            concat=False,
            edge_dim=1,
            add_self_loops=False,
        )

    def _encode(self, node_features: Tensor, adj: Tensor, edge_cost: Tensor) -> Tensor:
        edge_index, edge_attr = _dense_to_edge_index(adj, edge_cost)
        h = torch.relu(self.layer1(node_features, edge_index, edge_attr))
        return torch.relu(self.layer2(h, edge_index, edge_attr))

    def forward(
        self,
        node_features: Tensor,
        adj: Tensor,
        edge_cost: Tensor,
        agent_position: int,
    ) -> Tensor:
        """Run two GATv2 hops and return the encoding at `agent_position`."""
        h = self._encode(node_features, adj, edge_cost)
        if not 0 <= agent_position < h.size(0):
            raise IndexError(f"agent_position {agent_position} out of range for {h.size(0)} nodes")
        return h[agent_position]

    def forward_all(
        self,
        node_features: Tensor,
        adj: Tensor,
        edge_cost: Tensor,
    ) -> Tensor:
        """Run two GATv2 hops and return the full (n_nodes, hidden_dim) matrix.

        Convenient when the caller needs the embedding for every agent
        in a single batched query (one forward pass over the graph
        amortised across N agents).
        """
        return self._encode(node_features, adj, edge_cost)


__all__ = ["DEFAULT_HIDDEN_DIM", "SupplyGraphEncoder"]
