"""Phase 6a Tier 2 — Security ↔ Market / Logistics / FL.

Concept taught: a single security event (signing rejections crossing a
threshold) must propagate to the economic and learning loops so that a
compromised client cannot trade, cannot be picked as a logistics
carrier, and cannot poison the FL aggregate. We assert each step of
that propagation in isolation, then end-to-end via the orchestrator's
event handler and the public ``/security/blocked-agents`` endpoint.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from penumbra_core.arena import ArenaConfig
from penumbra_core.economy import Market
from penumbra_core.logistics import (
    CargoConstraints,
    LogisticsMempool,
    assign_carriers,
)
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_learning.federated import FederatedTrainer
from penumbra_learning.mappo import MAPPO, MAPPOConfig
from penumbra_transport.agent_signing import AgentKeystore
from penumbra_transport.api import build_app
from penumbra_transport.events import Event


def _build_sim(n_agents: int = 6, n_nodes: int = 10) -> Simulation:
    return Simulation.build(
        SimulationConfig(n_agents=n_agents, arena=ArenaConfig(n_nodes=n_nodes)),
        bootstrap(42),
    )


def _build_market(sim: Simulation) -> Market:
    return Market.build(
        nodes=list(sim.arena.graph.nodes()),
        n_agents=len(sim.agents),
        seed=42,
    )


# ── Keystore threshold + callback ─────────────────────────────────


def test_keystore_threshold_invokes_callback_with_until_tick() -> None:
    """3 rejections within the window must invoke ``on_agent_blocked``."""
    keystore = AgentKeystore.for_n_agents(3)
    captured: list[tuple[int, int]] = []
    keystore.on_agent_blocked = lambda agent_id, until_tick: captured.append((agent_id, until_tick))
    bogus_sig = b"\x00" * 32
    # Three rejections at tick 100 → cross threshold; one callback fires.
    for _ in range(3):
        keystore.verify_move(agent_id=1, tick=100, target_node=4, signature=bogus_sig)
    assert len(captured) == 1
    agent_id, until_tick = captured[0]
    assert agent_id == 1
    # cool-off is 600 ticks; until_tick = 100 + 600
    assert until_tick == 100 + 600


def test_keystore_threshold_does_not_count_old_rejections() -> None:
    """Rejections outside ``_TRADE_BLOCK_WINDOW_TICKS`` must not count."""
    keystore = AgentKeystore.for_n_agents(3)
    captured: list[tuple[int, int]] = []
    keystore.on_agent_blocked = lambda agent_id, until_tick: captured.append((agent_id, until_tick))
    bogus_sig = b"\x00" * 32
    # Two rejections in the distant past — should not count toward today's threshold.
    keystore.verify_move(agent_id=0, tick=0, target_node=2, signature=bogus_sig)
    keystore.verify_move(agent_id=0, tick=10, target_node=2, signature=bogus_sig)
    # One rejection at tick 1000 (outside the 300-tick window) — still no callback.
    keystore.verify_move(agent_id=0, tick=1000, target_node=2, signature=bogus_sig)
    assert captured == []


# ── Market.blocked_agents gates BUY/SELL ──────────────────────────


def test_market_block_agent_skips_trades_and_counts_attempts() -> None:
    sim = _build_sim()
    market = _build_market(sim)
    nodes = list(market.markets.keys())
    # Seed one wallet with inventory in a product the city stocks so a
    # SELL would otherwise occur.
    blocked_id = 0
    pid = market.markets[nodes[0]].stocked_products[0]
    market.wallets[blocked_id].inventory[pid] = 10
    rng = np.random.default_rng(7)

    # First arrival sets _previous_node; second arrival at a different node
    # is what would trigger a sell/buy. Without blocking we record any
    # trades; with blocking the attempt is counted instead.
    market.block_agent(blocked_id)
    market.settle_arrivals(tick=1, agent_positions={blocked_id: nodes[0]}, rng=rng)
    trades = market.settle_arrivals(tick=2, agent_positions={blocked_id: nodes[1]}, rng=rng)
    assert trades == []
    assert market.blocked_trade_attempts >= 1
    # After unblocking, the next arrival path is no longer skipped.
    market.unblock_agent(blocked_id)
    assert blocked_id not in market.blocked_agents


def test_market_block_agent_is_idempotent() -> None:
    market = _build_market(_build_sim())
    market.block_agent(2)
    market.block_agent(2)
    assert market.blocked_agents == {2}
    market.unblock_agent(99)  # unknown id is a no-op
    assert market.blocked_agents == {2}


# ── assign_carriers honours blocked_agents kw arg ─────────────────


def test_assign_carriers_skips_blocked_agent() -> None:
    """When only the blocked agent has capacity, n_assigned drops to 0."""
    sim = _build_sim(n_agents=2)
    market = _build_market(sim)
    cargo = CargoConstraints.uniform(n_agents=2)
    mempool = LogisticsMempool()
    city = next(iter(market.markets.keys()))
    pid = market.markets[city].stocked_products[0]
    mempool.place(city=city, product=pid, quantity=1, tick=0, reward=1.0)
    # Both agents start at the city so both have zero-distance candidacy.
    agent_positions = {0: city, 1: city}
    # Fill agent 1's inventory so only agent 0 has spare capacity.
    market.wallets[1].inventory[pid] = cargo.capacity[1]
    n = assign_carriers(
        mempool=mempool,
        market=market,
        arena=sim.arena,
        agent_positions=agent_positions,
        cargo=cargo,
        tick=1,
        blocked_agents={0},
    )
    assert n == 0
    # Without the block, agent 0 is picked.
    assert mempool.pending[0].assigned_to is None
    n2 = assign_carriers(
        mempool=mempool,
        market=market,
        arena=sim.arena,
        agent_positions=agent_positions,
        cargo=cargo,
        tick=2,
    )
    assert n2 == 1
    assert mempool.pending[0].assigned_to == 0


# ── FederatedTrainer.block_agent zeros that agent's delta ─────────


def test_federated_trainer_blocked_agent_delta_is_zero() -> None:
    cfg = MAPPOConfig(obs_dim=18, n_actions=7, n_agents=4, hidden=8)
    mappo = MAPPO(cfg)
    trainer = FederatedTrainer.from_mappo(mappo, n_agents=4)
    trainer.local_steps = 2
    rng = np.random.default_rng(13)
    # Seed buffers so every actor would produce a non-zero delta.
    for agent_id in trainer.local_actors:
        for _ in range(16):
            obs = rng.standard_normal(size=(18,)).astype(np.float32)
            trainer.ingest(agent_id, obs, int(rng.integers(0, 7)))
    # Force agent 2 to be blocked.
    trainer.block_agent(2)
    # Drive the local SGD phase so non-blocked actors actually mutate weights.
    trainer._local_phase()
    deltas, _ = trainer._collect_deltas()
    # Deltas are in insertion order; agent 2 is the 3rd entry (index 2).
    blocked_delta = deltas[2]
    for name, tensor in blocked_delta.items():
        assert torch.allclose(tensor, torch.zeros_like(tensor)), name
    trainer.unblock_agent(2)
    assert 2 not in trainer.blocked_agents


# ── Orchestrator end-to-end: event → block → unblock at until_tick ─


def _build_orchestrated_app() -> FastAPI:
    sim = _build_sim(n_agents=4, n_nodes=12)
    return build_app(sim, tick_hz=200.0)


def test_endpoint_reflects_block_and_unblock_after_cooloff() -> None:
    """Synthetic agent.blocked event → market blocked → endpoint payload."""
    app = _build_orchestrated_app()
    with TestClient(app) as client:
        orchestrator = app.state.penumbra.orchestrator  # type: ignore[attr-defined]
        # Inject a FederatedTrainer so the FL leg of the handler runs.
        cfg = MAPPOConfig(
            obs_dim=18,
            n_actions=7,
            n_agents=len(orchestrator.simulation.agents),
            hidden=8,
        )
        trainer = FederatedTrainer.from_mappo(
            MAPPO(cfg), n_agents=len(orchestrator.simulation.agents)
        )
        orchestrator.federated_trainer = trainer

        # Emit an agent.blocked event the same way the keystore would.
        current_tick = orchestrator.simulation.tick_counter
        until_tick = current_tick + 50
        orchestrator.event_bus.emit(
            Event(
                kind="agent.blocked",
                tick=current_tick,
                payload={
                    "agent_id": 1,
                    "reason": "signing_rejected",
                    "until_tick": until_tick,
                },
            )
        )

        body = client.get("/security/blocked-agents").json()
        assert body["history_count"] == 1
        ids = [row["agent_id"] for row in body["blocked"]]
        assert 1 in ids
        assert all(row["reason"] == "signing_rejected" for row in body["blocked"])
        assert 1 in orchestrator.market.blocked_agents
        assert 1 in trainer.blocked_agents

        # Drain at a tick past until_tick — the unblock fires.
        orchestrator._drain_pending_unblocks(until_tick + 1)
        body2 = client.get("/security/blocked-agents").json()
        assert all(row["agent_id"] != 1 for row in body2["blocked"])
        assert 1 not in orchestrator.market.blocked_agents
        assert 1 not in trainer.blocked_agents
        # History counter never decreases.
        assert body2["history_count"] == 1


def test_endpoint_exposes_blocked_trade_attempts_counter() -> None:
    app = _build_orchestrated_app()
    with TestClient(app) as client:
        orchestrator = app.state.penumbra.orchestrator  # type: ignore[attr-defined]
        market = orchestrator.market
        # Manually drive a gated trade attempt on a controlled positions dict.
        nodes = list(market.markets.keys())
        agent_id = 0
        market.block_agent(agent_id)
        rng = np.random.default_rng(2)
        market.settle_arrivals(tick=1, agent_positions={agent_id: nodes[0]}, rng=rng)
        market.settle_arrivals(tick=2, agent_positions={agent_id: nodes[1]}, rng=rng)
        body = client.get("/security/blocked-agents").json()
        assert body["blocked_trade_attempts"] >= 1


# ── Sanity guard against the API endpoint with no orchestrator state ──


def test_endpoint_is_callable_without_active_blocks() -> None:
    app = _build_orchestrated_app()
    with TestClient(app) as client:
        body = client.get("/security/blocked-agents").json()
        assert body["blocked"] == []
        assert body["history_count"] == 0
        assert body["blocked_trade_attempts"] == 0


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
