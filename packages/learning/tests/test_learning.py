"""Smoke tests for the learning stack.

We don't assert that MAPPO converges — that would be flaky. We assert
shapes, device, gradient flow, and round-trip save/load.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
import torch
from penumbra_learning.device import best_device
from penumbra_learning.env import NEIGHBOURS_K, OBS_PER_NEIGHBOUR, PenumbraEnv
from penumbra_learning.gat_pathfinder import GATv2Layer, GATv2Pathfinder
from penumbra_learning.mappo import MAPPO, MAPPOConfig

# ── device ────────────────────────────────────────────────────────


def test_best_device_returns_something_usable() -> None:
    device = best_device()
    x = torch.randn(2, 2, device=device)
    assert x.device.type in {"cpu", "mps", "cuda"}
    assert torch.isfinite(x.sum()).item()


# ── env ───────────────────────────────────────────────────────────


def test_env_reset_returns_per_agent_observations() -> None:
    env = PenumbraEnv(n_agents=8, arena_nodes=15)
    obs, infos = env.reset(seed=42)
    assert len(obs) == 8
    assert all(o.shape == (NEIGHBOURS_K * OBS_PER_NEIGHBOUR,) for o in obs.values())
    assert len(infos) == 8


def test_env_step_advances_simulation() -> None:
    env = PenumbraEnv(n_agents=5, arena_nodes=12)
    env.reset(seed=42)
    actions = dict.fromkeys(env.possible_agents, 0)
    obs, rewards, terminated, truncated, _ = env.step(actions)
    assert set(obs.keys()) == set(env.possible_agents)
    assert all(isinstance(r, float) for r in rewards.values())
    assert all(isinstance(t, bool) for t in terminated.values())
    assert all(isinstance(t, bool) for t in truncated.values())


def test_env_reset_is_deterministic_with_same_seed() -> None:
    env = PenumbraEnv(n_agents=5, arena_nodes=12)
    obs1, _ = env.reset(seed=42)
    obs2, _ = env.reset(seed=42)
    for a in obs1:
        np.testing.assert_array_equal(obs1[a], obs2[a])


# ── GATv2 ─────────────────────────────────────────────────────────


def test_gat_layer_shape() -> None:
    layer = GATv2Layer(in_dim=4, out_dim=8)
    x = torch.randn(10, 4)
    adj = torch.eye(10, dtype=torch.bool) | (torch.randn(10, 10) > 0.5)
    edge_cost = torch.rand(10, 10)
    out = layer(x, adj, edge_cost)
    assert out.shape == (10, 8)
    assert torch.isfinite(out).all()


def test_gat_pathfinder_per_node_output() -> None:
    model = GATv2Pathfinder(in_dim=2, hidden_dim=16, out_dim=1)
    x = torch.randn(12, 2)
    adj = torch.eye(12, dtype=torch.bool) | (torch.randn(12, 12) > 0.3)
    edge_cost = torch.rand(12, 12)
    out = model(x, adj, edge_cost)
    assert out.shape == (12,)


def test_gat_gradients_flow() -> None:
    model = GATv2Pathfinder(in_dim=2, hidden_dim=8, out_dim=1)
    x = torch.randn(6, 2, requires_grad=True)
    adj = torch.eye(6, dtype=torch.bool) | (torch.rand(6, 6) > 0.4)
    edge_cost = torch.rand(6, 6)
    out = model(x, adj, edge_cost).sum()
    out.backward()
    assert x.grad is not None
    assert torch.isfinite(x.grad).all()


# ── MAPPO ─────────────────────────────────────────────────────────


def _config(n_agents: int = 5) -> MAPPOConfig:
    return MAPPOConfig(
        obs_dim=NEIGHBOURS_K * OBS_PER_NEIGHBOUR,
        n_actions=NEIGHBOURS_K + 1,
        n_agents=n_agents,
        hidden=16,
        ppo_epochs=2,
        minibatch_size=16,
    )


def test_mappo_construction_and_inference() -> None:
    agent = MAPPO(_config())
    obs = (
        np.random.default_rng(seed=0)
        .standard_normal((5, NEIGHBOURS_K * OBS_PER_NEIGHBOUR))
        .astype(np.float32)
    )
    actions = agent.act(obs)
    assert actions.shape == (5,)
    assert (actions >= 0).all()
    assert (actions < NEIGHBOURS_K + 1).all()


def test_mappo_save_load_roundtrip() -> None:
    agent = MAPPO(_config())
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "ckpt.pt"
        agent.save(str(path))
        reload = MAPPO(_config())
        reload.load(str(path))
    # Same network → same outputs for the same input.
    obs = np.zeros((5, NEIGHBOURS_K * OBS_PER_NEIGHBOUR), dtype=np.float32)
    a1 = agent.act(obs, deterministic=True)
    a2 = reload.act(obs, deterministic=True)
    np.testing.assert_array_equal(a1, a2)


@pytest.mark.slow
def test_mappo_update_reduces_critic_loss_on_constant_returns() -> None:
    """If we feed the critic a constant target, its loss should monotonically
    decrease across iterations (sanity check on the gradient direction).

    Marked `slow`: 45 s on CPU — the assertion needs enough PPO steps for
    the loss curve to be visibly monotone.
    """
    agent = MAPPO(_config(n_agents=2))
    device = agent.device
    obs_dim = NEIGHBOURS_K * OBS_PER_NEIGHBOUR
    t_steps = 32

    obs_batch = torch.zeros(t_steps, 2, obs_dim, device=device)
    global_obs_batch = torch.zeros(t_steps, 2 * obs_dim, device=device)
    actions_batch = torch.zeros(t_steps, 2, dtype=torch.long, device=device)
    log_probs_old = torch.zeros(t_steps, 2, device=device)
    advantages = torch.randn(t_steps, 2, device=device)
    returns = torch.ones(t_steps, device=device) * 5.0  # constant target

    losses: list[float] = []
    for _ in range(5):
        metrics = agent.update(
            obs_batch=obs_batch,
            global_obs_batch=global_obs_batch,
            actions_batch=actions_batch,
            log_probs_old=log_probs_old,
            advantages=advantages,
            returns=returns,
        )
        losses.append(metrics["critic_loss"])
    assert losses[-1] < losses[0]


# ── env + agent integration ──────────────────────────────────────


@pytest.mark.slow
def test_env_agent_roundtrip() -> None:
    """One full rollout: env.reset → MAPPO.act → env.step, ~20 ticks."""
    env = PenumbraEnv(n_agents=5, arena_nodes=12, max_match_ticks=30)
    config = _config(n_agents=5)
    agent = MAPPO(config)
    obs_dict, _ = env.reset(seed=42)
    for _ in range(20):
        obs_array = np.stack([obs_dict[a] for a in env.possible_agents])
        actions_np = agent.act(obs_array.astype(np.float32))
        actions_dict = {a: int(actions_np[i]) for i, a in enumerate(env.possible_agents)}
        obs_dict, _rewards, terminated, _truncated, _infos = env.step(actions_dict)
        if all(terminated.values()):
            obs_dict, _ = env.reset(seed=42)
