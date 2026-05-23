"""Tests for the Tier-4 LogisticsRewardShaper.

Concept tested: logistics KPIs (fulfilment, stale assignments, fill
rate) translate into per-agent reward signals when the corresponding
weight is non-zero, AND stay perfectly neutral when the weights are
zero (the backward-compatibility guarantee for existing MAPPO runs).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from penumbra_learning.env import REWARD_WEIGHTS, PenumbraEnv, RewardWeights
from penumbra_learning.logistics_shaper import LogisticsRewardShaper


@dataclass(slots=True)
class StubOrder:
    """Minimal Order-like object that the shaper reads via getattr."""

    id: int
    assigned_to: int | None = None
    fulfilled_by: int | None = None


@dataclass(slots=True)
class StubMempool:
    pending: list[Any] = field(default_factory=list)
    fulfilled: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class StubDemand:
    cumulative_served: int = 0
    cumulative_requested: int = 0


@pytest.fixture(autouse=True)
def reset_global_weights() -> Any:
    """Snapshot + restore REWARD_WEIGHTS so tests don't leak global state."""
    snapshot = (
        REWARD_WEIGHTS.goal_reward,
        REWARD_WEIGHTS.step_penalty,
        REWARD_WEIGHTS.illegal_move_penalty,
        REWARD_WEIGHTS.crowding_penalty,
        REWARD_WEIGHTS.logistics_dispatch_bonus,
        REWARD_WEIGHTS.logistics_dispatch_penalty,
        REWARD_WEIGHTS.fill_rate_bonus,
    )
    yield
    (
        REWARD_WEIGHTS.goal_reward,
        REWARD_WEIGHTS.step_penalty,
        REWARD_WEIGHTS.illegal_move_penalty,
        REWARD_WEIGHTS.crowding_penalty,
        REWARD_WEIGHTS.logistics_dispatch_bonus,
        REWARD_WEIGHTS.logistics_dispatch_penalty,
        REWARD_WEIGHTS.fill_rate_bonus,
    ) = snapshot


# ── default neutrality ───────────────────────────────────────────


def test_default_weights_zero_contribution() -> None:
    shaper = LogisticsRewardShaper(
        mempool=StubMempool(fulfilled=[StubOrder(id=1, fulfilled_by=0)]),
        demand=StubDemand(cumulative_served=10, cumulative_requested=20),
    )
    weights = RewardWeights()  # all logistics fields default to 0.0
    out = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=[f"agent_{i}" for i in range(3)],
        is_terminal=True,
        weights=weights,
    )
    assert all(v == 0.0 for v in out.values()), (
        f"default weights should produce zero rewards, got {out}"
    )


def test_env_with_default_weights_unchanged_total_reward() -> None:
    """End-to-end: a real PenumbraEnv with shaping enabled but weights=0
    must produce IDENTICAL rewards to the same env without shaping."""
    env_plain = PenumbraEnv(n_agents=3, arena_nodes=8, seed=7)
    env_plain.reset(seed=7)
    actions = dict.fromkeys(env_plain.possible_agents, 0)
    _, plain_rewards, _, _, _ = env_plain.step(actions)

    env_shaped = PenumbraEnv(n_agents=3, arena_nodes=8, seed=7, enable_logistics_rewards=True)
    env_shaped.reset(seed=7)
    _, shaped_rewards, _, _, _ = env_shaped.step(actions)

    for k in plain_rewards:
        assert plain_rewards[k] == pytest.approx(shaped_rewards[k]), (
            f"with default (zero) logistics weights, agent {k} reward must match"
        )


# ── dispatch bonus ───────────────────────────────────────────────


def test_dispatch_bonus_credits_the_fulfilling_agent() -> None:
    weights = RewardWeights(logistics_dispatch_bonus=1.0)
    mempool = StubMempool()
    shaper = LogisticsRewardShaper(mempool=mempool, demand=StubDemand())

    # Tick 1: no orders fulfilled — everyone gets 0.
    rewards = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0", "agent_1"],
        is_terminal=False,
        weights=weights,
    )
    assert rewards == {"agent_0": 0.0, "agent_1": 0.0}

    # Tick 2: agent_0 fulfilled order #1.
    mempool.fulfilled.append(StubOrder(id=1, fulfilled_by=0))
    rewards = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0", "agent_1"],
        is_terminal=False,
        weights=weights,
    )
    assert rewards["agent_0"] == pytest.approx(1.0)
    assert rewards["agent_1"] == pytest.approx(0.0)


def test_dispatch_bonus_not_double_credited() -> None:
    """A fulfilled order is rewarded ONCE across ticks, not every tick."""
    weights = RewardWeights(logistics_dispatch_bonus=1.0)
    mempool = StubMempool(fulfilled=[StubOrder(id=1, fulfilled_by=0)])
    shaper = LogisticsRewardShaper(mempool=mempool, demand=StubDemand())

    first = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=False,
        weights=weights,
    )
    second = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=False,
        weights=weights,
    )
    assert first["agent_0"] == pytest.approx(1.0)
    assert second["agent_0"] == pytest.approx(0.0)


def test_dispatch_bonus_ignores_phantom_carrier() -> None:
    """Orders fulfilled by carrier -1 (the safety fallback) are skipped."""
    weights = RewardWeights(logistics_dispatch_bonus=1.0)
    mempool = StubMempool(fulfilled=[StubOrder(id=1, fulfilled_by=-1)])
    shaper = LogisticsRewardShaper(mempool=mempool, demand=StubDemand())
    rewards = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=False,
        weights=weights,
    )
    assert rewards["agent_0"] == 0.0


# ── dispatch penalty ─────────────────────────────────────────────


def test_dispatch_penalty_charges_after_first_observation() -> None:
    """The penalty kicks in on the SECOND tick an order remains assigned
    (first tick is the assignment grace period)."""
    weights = RewardWeights(logistics_dispatch_penalty=0.5)
    order = StubOrder(id=1, assigned_to=0)
    mempool = StubMempool(pending=[order])
    shaper = LogisticsRewardShaper(mempool=mempool, demand=StubDemand())

    # Tick 1: grace — no penalty applied yet.
    out1 = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=False,
        weights=weights,
    )
    assert out1["agent_0"] == pytest.approx(0.0)

    # Tick 2: penalty applied — agent_0 loses 0.5.
    out2 = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=False,
        weights=weights,
    )
    assert out2["agent_0"] == pytest.approx(-0.5)

    # Tick 3: still penalised because the assignment is still pending.
    out3 = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=False,
        weights=weights,
    )
    assert out3["agent_0"] == pytest.approx(-0.5)


def test_dispatch_penalty_clears_after_fulfilment() -> None:
    weights = RewardWeights(logistics_dispatch_penalty=0.5)
    order = StubOrder(id=1, assigned_to=0)
    mempool = StubMempool(pending=[order])
    shaper = LogisticsRewardShaper(mempool=mempool, demand=StubDemand())

    # Burn the grace tick + one penalty tick.
    shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=False,
        weights=weights,
    )
    shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=False,
        weights=weights,
    )

    # Fulfil the order: pending → fulfilled.
    mempool.pending.clear()
    mempool.fulfilled.append(StubOrder(id=1, fulfilled_by=0))

    # No more pending assignment → no penalty.
    out = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=False,
        weights=weights,
    )
    assert out["agent_0"] == pytest.approx(0.0)


# ── fill rate bonus ──────────────────────────────────────────────


def test_fill_rate_bonus_applied_only_at_terminal_tick() -> None:
    weights = RewardWeights(fill_rate_bonus=10.0)
    demand = StubDemand(cumulative_served=8, cumulative_requested=10)
    shaper = LogisticsRewardShaper(mempool=StubMempool(), demand=demand)

    # Non-terminal: zero.
    mid = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0", "agent_1"],
        is_terminal=False,
        weights=weights,
    )
    assert all(v == 0.0 for v in mid.values())

    # Terminal: every agent receives 10 * 0.8 = 8.0.
    end = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0", "agent_1"],
        is_terminal=True,
        weights=weights,
    )
    assert end["agent_0"] == pytest.approx(8.0)
    assert end["agent_1"] == pytest.approx(8.0)


def test_fill_rate_bonus_zero_when_no_demand_recorded() -> None:
    weights = RewardWeights(fill_rate_bonus=10.0)
    shaper = LogisticsRewardShaper(mempool=StubMempool(), demand=StubDemand())
    out = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=True,
        weights=weights,
    )
    assert out["agent_0"] == 0.0


def test_fill_rate_bonus_terminal_applied_once() -> None:
    """The terminal bonus is paid exactly once per episode lifetime."""
    weights = RewardWeights(fill_rate_bonus=10.0)
    demand = StubDemand(cumulative_served=5, cumulative_requested=10)
    shaper = LogisticsRewardShaper(mempool=StubMempool(), demand=demand)

    first = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=True,
        weights=weights,
    )
    second = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=True,
        weights=weights,
    )
    assert first["agent_0"] == pytest.approx(5.0)
    assert second["agent_0"] == pytest.approx(0.0)


def test_reset_re_enables_terminal_bonus() -> None:
    """After `reset()` the shaper is ready to pay another terminal bonus."""
    weights = RewardWeights(fill_rate_bonus=10.0)
    demand = StubDemand(cumulative_served=5, cumulative_requested=10)
    shaper = LogisticsRewardShaper(mempool=StubMempool(), demand=demand)

    shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=True,
        weights=weights,
    )
    shaper.reset()
    again = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=True,
        weights=weights,
    )
    assert again["agent_0"] == pytest.approx(5.0)


# ── env wiring (no orchestrator → graceful no-op) ─────────────────


def test_env_step_with_shaper_no_mempool_returns_clean() -> None:
    """When the env has no orchestrator state, the shaper must not crash."""
    env = PenumbraEnv(n_agents=3, arena_nodes=8, seed=11, enable_logistics_rewards=True)
    env.reset(seed=11)
    REWARD_WEIGHTS.logistics_dispatch_bonus = 5.0
    REWARD_WEIGHTS.fill_rate_bonus = 5.0
    actions = dict.fromkeys(env.possible_agents, 0)
    _obs, rewards, _terminated, _truncated, _ = env.step(actions)
    # No mempool / no demand attached to the sim → no logistics contribution.
    # Rewards must still be finite floats keyed by every possible agent.
    assert set(rewards.keys()) == set(env.possible_agents)
    assert all(isinstance(v, float) for v in rewards.values())
