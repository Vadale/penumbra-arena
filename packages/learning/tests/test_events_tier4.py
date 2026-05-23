"""Tier 4 — ML/RL ↔ Logistics reward feedback (Phase 6a).

Concept tested: the LiveTrainer's env reads live orchestrator state
through ``LogisticsRewardShaper``, every PPO iteration emits a
``ml.policy.updated`` event, and the orchestrator turns sustained
reward jumps into a downstream ``policy.improved`` event the
dashboard can consume.

Spec: INTER_SILO_INTEGRATION_PLAN.md §Tier 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from penumbra_core.logistics import LogisticsMempool
from penumbra_learning.env import REWARD_WEIGHTS, PenumbraEnv
from penumbra_learning.live_trainer import LiveTrainer
from penumbra_learning.logistics_shaper import LogisticsRewardShaper
from penumbra_learning.mappo import MAPPO, MAPPOConfig
from penumbra_transport.events import Event, EventBus


@pytest.fixture(autouse=True)
def reset_global_weights() -> Any:
    """Snapshot + restore REWARD_WEIGHTS so tests don't leak state."""
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


@dataclass(slots=True)
class _StubDemand:
    cumulative_served: int = 0
    cumulative_requested: int = 0


@dataclass(slots=True)
class _StubOrchestrator:
    """Smallest orchestrator-like with the fields the env / trainer reads."""

    logistics_mempool: LogisticsMempool = field(default_factory=LogisticsMempool)
    demand: _StubDemand = field(default_factory=_StubDemand)
    event_bus: EventBus = field(default_factory=EventBus)
    simulation: object = field(default=None)


# ── env <-> orchestrator wiring ──────────────────────────────────


def test_env_with_orchestrator_reads_live_mempool() -> None:
    """When an orchestrator is wired, the env's shaper sees its mempool."""
    orch = _StubOrchestrator()
    env = PenumbraEnv(n_agents=3, arena_nodes=8, seed=11, orchestrator=orch)
    env.reset(seed=11)
    REWARD_WEIGHTS.logistics_dispatch_bonus = 2.0
    # Inject a synthetic order then fulfil it by agent 1.
    order = orch.logistics_mempool.place(
        city=0, product=0, quantity=1, tick=0, reward=1.0, assigned_to=1
    )
    orch.logistics_mempool.fulfil(order_id=order.id, agent_id=1, tick=0)
    actions = dict.fromkeys(env.possible_agents, 0)
    _obs, rewards, _term, _trunc, _ = env.step(actions)
    # The shaper should credit agent_1 with the dispatch bonus.
    assert rewards["agent_1"] > rewards["agent_0"]
    assert rewards["agent_1"] - rewards["agent_0"] == pytest.approx(2.0, rel=1e-6)


def test_env_without_orchestrator_unchanged_behaviour() -> None:
    """No orchestrator → shaping is a no-op; matches plain env rewards."""
    env_plain = PenumbraEnv(n_agents=3, arena_nodes=8, seed=11)
    env_plain.reset(seed=11)
    actions = dict.fromkeys(env_plain.possible_agents, 0)
    _, plain_rewards, _, _, _ = env_plain.step(actions)

    env_shaped = PenumbraEnv(n_agents=3, arena_nodes=8, seed=11, enable_logistics_rewards=True)
    env_shaped.reset(seed=11)
    _, shaped_rewards, _, _, _ = env_shaped.step(actions)

    for k in plain_rewards:
        assert plain_rewards[k] == pytest.approx(shaped_rewards[k])


# ── shaper uses recent_carrier_rewards fast path ─────────────────


def test_shaper_reads_recent_carrier_rewards_deque() -> None:
    """The shaper credits agents listed in the deque, not via fulfilled-walk."""
    mempool = LogisticsMempool()
    order = mempool.place(city=0, product=0, quantity=1, tick=0, reward=1.0, assigned_to=2)
    mempool.fulfil(order_id=order.id, agent_id=2, tick=0)
    # Deque has one (2, 1.0) entry; total_carrier_fulfilments == 1.
    assert list(mempool.recent_carrier_rewards) == [(2, 1.0)]
    assert mempool.total_carrier_fulfilments == 1

    shaper = LogisticsRewardShaper(mempool=mempool, demand=_StubDemand())  # type: ignore[arg-type]
    REWARD_WEIGHTS.logistics_dispatch_bonus = 3.0
    out = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0", "agent_1", "agent_2"],
        is_terminal=False,
        weights=REWARD_WEIGHTS,
    )
    assert out["agent_2"] == pytest.approx(3.0)
    assert out["agent_0"] == pytest.approx(0.0)
    assert out["agent_1"] == pytest.approx(0.0)


def test_shaper_does_not_double_credit_via_deque() -> None:
    """A fulfilled order is credited exactly once across multiple shaper steps."""
    mempool = LogisticsMempool()
    order = mempool.place(city=0, product=0, quantity=1, tick=0, reward=1.0, assigned_to=0)
    mempool.fulfil(order_id=order.id, agent_id=0, tick=0)
    shaper = LogisticsRewardShaper(mempool=mempool, demand=_StubDemand())  # type: ignore[arg-type]
    REWARD_WEIGHTS.logistics_dispatch_bonus = 1.0
    first = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=False,
        weights=REWARD_WEIGHTS,
    )
    second = shaper.step(
        sim=None,  # type: ignore[arg-type]
        possible_agents=["agent_0"],
        is_terminal=False,
        weights=REWARD_WEIGHTS,
    )
    assert first["agent_0"] == pytest.approx(1.0)
    assert second["agent_0"] == pytest.approx(0.0)


def test_phantom_carrier_not_recorded_in_deque() -> None:
    """Phantom (-1) carriers must not pollute the carrier-rewards stream."""
    mempool = LogisticsMempool()
    order_real = mempool.place(city=0, product=0, quantity=1, tick=0, reward=2.0, assigned_to=4)
    order_phantom = mempool.place(city=0, product=0, quantity=1, tick=0, reward=2.0)
    mempool.fulfil(order_id=order_real.id, agent_id=4, tick=0)
    mempool.fulfil(order_id=order_phantom.id, agent_id=-1, tick=0)
    assert list(mempool.recent_carrier_rewards) == [(4, 2.0)]
    assert mempool.total_carrier_fulfilments == 1


# ── LiveTrainer emits ml.policy.updated ──────────────────────────


def _tiny_mappo(n_agents: int) -> MAPPO:
    """Smallest MAPPO that matches the env's observation/action layout."""
    from penumbra_learning.env import NEIGHBOURS_K, OBS_PER_NEIGHBOUR

    return MAPPO(
        MAPPOConfig(
            obs_dim=NEIGHBOURS_K * OBS_PER_NEIGHBOUR,
            n_actions=NEIGHBOURS_K + 1,
            n_agents=n_agents,
            hidden=8,
            ppo_epochs=1,
            minibatch_size=8,
        )
    )


def test_live_trainer_emits_policy_updated_each_iter() -> None:
    """Every PPO iter publishes one ml.policy.updated event."""
    n_agents = 3
    orch = _StubOrchestrator()
    trainer = LiveTrainer(
        agent_net=_tiny_mappo(n_agents),
        n_env_agents=n_agents,
        rollout_length=8,
        orchestrator=orch,
    )
    seen: list[Event] = []
    orch.event_bus.subscribe("ml.policy.updated", seen.append)
    trainer._one_iteration()
    trainer._one_iteration()
    assert len(seen) == 2
    for evt in seen:
        assert "iteration" in evt.payload
        assert "mean_reward" in evt.payload
        assert "kl" in evt.payload


# ── orchestrator emits policy.improved on >50% reward jump ───────


def test_policy_improved_fires_on_large_reward_jump() -> None:
    """ml.policy.updated → orchestrator emits policy.improved when ratio>1.5."""
    from penumbra_core.arena import ArenaConfig
    from penumbra_core.rng import bootstrap
    from penumbra_core.simulation import Simulation, SimulationConfig
    from penumbra_transport.orchestrator import Orchestrator

    seeded = bootstrap(42)
    sim = Simulation.build(
        SimulationConfig(n_agents=3, arena=ArenaConfig(n_nodes=6)),
        seeded,
    )
    orch = Orchestrator.build(sim)
    seen: list[Event] = []
    orch.event_bus.subscribe("policy.improved", seen.append)

    # First update seeds the baseline; no improvement event yet.
    orch.event_bus.emit(
        Event(
            kind="ml.policy.updated",
            tick=1,
            payload={"iteration": 1, "mean_reward": 1.0, "kl": 0.01},
        )
    )
    assert seen == []

    # Second update with reward > 1.5 * baseline (=1.0) → improvement.
    orch.event_bus.emit(
        Event(
            kind="ml.policy.updated",
            tick=2,
            payload={"iteration": 2, "mean_reward": 2.0, "kl": 0.02},
        )
    )
    assert len(seen) == 1
    assert seen[0].payload["iteration"] == 2
    assert float(seen[0].payload["ratio"]) > 1.5  # type: ignore[arg-type]
    assert orch._policy_improvements[-1].kind == "policy.improved"


def test_policy_improved_silent_on_small_jump() -> None:
    """Sub-50% reward jumps do NOT trigger policy.improved."""
    from penumbra_core.arena import ArenaConfig
    from penumbra_core.rng import bootstrap
    from penumbra_core.simulation import Simulation, SimulationConfig
    from penumbra_transport.orchestrator import Orchestrator

    seeded = bootstrap(7)
    sim = Simulation.build(
        SimulationConfig(n_agents=3, arena=ArenaConfig(n_nodes=6)),
        seeded,
    )
    orch = Orchestrator.build(sim)
    seen: list[Event] = []
    orch.event_bus.subscribe("policy.improved", seen.append)

    orch.event_bus.emit(
        Event(
            kind="ml.policy.updated",
            tick=1,
            payload={"iteration": 1, "mean_reward": 1.0, "kl": 0.0},
        )
    )
    orch.event_bus.emit(
        Event(
            kind="ml.policy.updated",
            tick=2,
            payload={"iteration": 2, "mean_reward": 1.2, "kl": 0.0},
        )
    )
    assert seen == []
