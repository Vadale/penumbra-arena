"""Tests for the Tier-4 SupplyGraphEncoder.

Concept tested: the encoder takes a small supply graph + an agent's
position and returns a fixed-size embedding (gradient-friendly so it
can be trained jointly with the actor).
"""

from __future__ import annotations

import pytest
import torch
from penumbra_learning.supply_gnn import DEFAULT_HIDDEN_DIM, SupplyGraphEncoder


def _build_5_node_graph() -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    n_nodes = 5
    in_dim = 3
    node_features = torch.randn(n_nodes, in_dim)
    # Simple ring + self-loops so every node has 3 neighbours (self, prev, next).
    adj = torch.zeros(n_nodes, n_nodes, dtype=torch.bool)
    for i in range(n_nodes):
        adj[i, i] = True
        adj[i, (i - 1) % n_nodes] = True
        adj[i, (i + 1) % n_nodes] = True
    edge_cost = torch.rand(n_nodes, n_nodes)
    return node_features, adj, edge_cost


def test_encoder_output_shape_matches_hidden_dim() -> None:
    encoder = SupplyGraphEncoder(in_dim=3, hidden_dim=DEFAULT_HIDDEN_DIM)
    x, adj, cost = _build_5_node_graph()
    embedding = encoder(x, adj, cost, agent_position=2)
    assert embedding.shape == (DEFAULT_HIDDEN_DIM,)
    assert torch.isfinite(embedding).all()


def test_encoder_forward_all_returns_full_matrix() -> None:
    encoder = SupplyGraphEncoder(in_dim=3, hidden_dim=24)
    x, adj, cost = _build_5_node_graph()
    full = encoder.forward_all(x, adj, cost)
    assert full.shape == (5, 24)
    assert torch.isfinite(full).all()


def test_encoder_supports_custom_hidden_dim_in_range() -> None:
    for hd in (8, 16, 32, 64):
        encoder = SupplyGraphEncoder(in_dim=3, hidden_dim=hd)
        x, adj, cost = _build_5_node_graph()
        emb = encoder(x, adj, cost, agent_position=0)
        assert emb.shape == (hd,)


def test_encoder_rejects_hidden_dim_outside_budget() -> None:
    with pytest.raises(ValueError, match="hidden_dim"):
        SupplyGraphEncoder(in_dim=3, hidden_dim=4)
    with pytest.raises(ValueError, match="hidden_dim"):
        SupplyGraphEncoder(in_dim=3, hidden_dim=128)


def test_encoder_rejects_out_of_range_position() -> None:
    encoder = SupplyGraphEncoder(in_dim=3, hidden_dim=16)
    x, adj, cost = _build_5_node_graph()
    with pytest.raises(IndexError):
        encoder(x, adj, cost, agent_position=42)


def test_encoder_gradient_flows_through_node_features() -> None:
    encoder = SupplyGraphEncoder(in_dim=3, hidden_dim=16)
    x, adj, cost = _build_5_node_graph()
    x.requires_grad_(True)
    embedding = encoder(x, adj, cost, agent_position=1)
    loss = embedding.sum()
    loss.backward()
    assert x.grad is not None
    assert torch.isfinite(x.grad).all()
    assert x.grad.abs().sum().item() > 0, "gradient should propagate to node features"


def test_encoder_gradient_flows_through_parameters() -> None:
    encoder = SupplyGraphEncoder(in_dim=3, hidden_dim=16)
    x, adj, cost = _build_5_node_graph()
    embedding = encoder(x, adj, cost, agent_position=0)
    loss = embedding.pow(2).sum()
    loss.backward()
    grads_present = [
        p.grad is not None and p.grad.abs().sum().item() > 0
        for p in encoder.parameters()
        if p.requires_grad
    ]
    assert any(grads_present), "at least one trainable parameter must receive a gradient"
