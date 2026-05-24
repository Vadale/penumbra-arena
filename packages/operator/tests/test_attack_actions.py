"""Tier 3 — operator attack actions.

Concept taught: the operator's attack catalogue is just six adapters
that dispatch into the Phase 5 ``penumbra_attacker.attacks`` modules.
Each handler returns the standard ``OperatorActionResult`` envelope
with ``data = {accepted, evidence, defender_response}`` and emits an
``Event(kind="operator.attack", ...)`` on the orchestrator's event bus
so the dashboard event log + any simulated victims can subscribe.

The tests in this file are 6 x (happy + failure) = 12 cases plus a
shared assertion that every successful attack reaches the event bus.
"""

from __future__ import annotations

from typing import Any

from penumbra_core.arena import ArenaConfig
from penumbra_core.economy import Market, Wallet
from penumbra_core.logistics import LogisticsMempool
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_crypto.dp import DPMechanism, PrivacyBudget
from penumbra_operator.actions import (
    ATTACK_KINDS,
    OperatorAction,
    OperatorContext,
    apply_action,
)
from penumbra_transport.agent_signing import AgentKeystore
from penumbra_transport.events import EventBus


def _build_context(
    *, with_bus: bool = True, n_agents: int = 4, operator_coins: float = 100.0
) -> tuple[OperatorContext, list[Any]]:
    """Spin up an OperatorContext + a captured event log.

    The returned list grows whenever an ``operator.attack`` event is
    emitted on the bundled bus; callers assert on its contents.
    """
    sim = Simulation.build(
        SimulationConfig(n_agents=n_agents, arena=ArenaConfig(n_nodes=15)),
        bootstrap(42),
    )
    from penumbra_core.agent import Agent, random_walk_policy

    operator_id = n_agents
    spawn = int(next(iter(sim.arena.graph.nodes())))
    operator_agent = Agent(id=operator_id, position=spawn, policy=random_walk_policy, home=spawn)
    sim.operator_agent = operator_agent
    market = Market.build(
        nodes=list(sim.arena.graph.nodes()),
        n_agents=n_agents,
        seed=42,
    )
    market.wallets[operator_id] = Wallet(agent_id=operator_id, coins=operator_coins)
    keystore = AgentKeystore.for_n_agents(n_agents + 1)
    bus: EventBus | None = EventBus() if with_bus else None
    captured: list[Any] = []
    if bus is not None:
        bus.subscribe("operator.attack", lambda e: captured.append(e))
    ctx = OperatorContext(
        simulation=sim,
        operator_agent=operator_agent,
        operator_agent_id=operator_id,
        market=market,
        mempool=LogisticsMempool(),
        dp_mechanism=DPMechanism(PrivacyBudget(epsilon=10.0)),
        keystore=keystore,
        initial_coins=operator_coins,
        event_bus=bus,
    )
    return ctx, captured


def _action(kind: str, payload: dict[str, Any], *, tick: int = 0) -> OperatorAction:
    return OperatorAction(kind=kind, payload=payload, submit_tick=tick)


# ── Happy paths ────────────────────────────────────────────────────


def test_attack_replay_happy_returns_envelope_and_emits_event() -> None:
    ctx, captured = _build_context()
    sig_hex = "ab" * 32
    result = apply_action(
        ctx,
        _action(
            "attack_replay",
            {"target_signature_hex": sig_hex, "replay_offset": 5},
        ),
    )
    assert result.success
    assert set(result.data.keys()) >= {"accepted", "evidence", "defender_response"}
    assert isinstance(result.data["accepted"], bool)
    assert result.data["evidence"]["target_signature_hex"] == sig_hex
    assert len(captured) == 1
    assert captured[0].kind == "operator.attack"
    assert captured[0].payload["kind"] == "attack_replay"


def test_attack_byzantine_happy_returns_envelope_and_emits_event() -> None:
    ctx, captured = _build_context()
    result = apply_action(ctx, _action("attack_byzantine", {"n_equivocations": 2}))
    assert result.success
    assert "accepted" in result.data
    assert result.data["evidence"]["n_equivocations"] == 2
    assert any(e.payload["kind"] == "attack_byzantine" for e in captured)


def test_attack_dp_recon_happy_returns_envelope_and_emits_event() -> None:
    ctx, captured = _build_context()
    log = [{"q": i, "noise": 0.1} for i in range(20)]
    result = apply_action(
        ctx,
        _action("attack_dp_recon", {"target_agent": 1, "query_log": log}),
    )
    assert result.success
    assert result.data["evidence"]["target_agent"] == 1
    assert any(e.payload["kind"] == "attack_dp_recon" for e in captured)


def test_attack_linkability_happy_returns_envelope_and_emits_event() -> None:
    ctx, captured = _build_context()
    result = apply_action(
        ctx,
        _action(
            "attack_linkability",
            {"feature_set": ["mean_pos", "top_visits"], "target_agent": 2},
        ),
    )
    assert result.success
    assert result.data["evidence"]["target_agent"] == 2
    assert any(e.payload["kind"] == "attack_linkability" for e in captured)


def test_attack_membership_happy_returns_envelope_and_emits_event() -> None:
    ctx, captured = _build_context()
    obs = [0.1, 0.2, 0.3, 0.4]
    result = apply_action(ctx, _action("attack_membership", {"target_observation": obs}))
    assert result.success
    assert result.data["evidence"]["n_features"] == 4
    assert any(e.payload["kind"] == "attack_membership" for e in captured)


def test_attack_snark_forge_happy_returns_envelope_and_emits_event() -> None:
    ctx, captured = _build_context()
    result = apply_action(ctx, _action("attack_snark_forge", {"circuit": "legal_path"}))
    # Whether artifacts are present or not, the handler returns
    # success=True (success of dispatch, not of the forge).
    assert result.success
    assert result.data["evidence"]["circuit"] == "legal_path"
    assert any(e.payload["kind"] == "attack_snark_forge" for e in captured)


# ── Failure paths ──────────────────────────────────────────────────


def test_attack_replay_failure_on_bad_payload() -> None:
    ctx, _ = _build_context()
    result = apply_action(
        ctx,
        _action("attack_replay", {"replay_offset": 0}),  # missing target sig
    )
    assert not result.success
    assert result.error is not None
    assert result.error["code"] == "bad_payload"


def test_attack_byzantine_failure_on_bad_payload() -> None:
    ctx, _ = _build_context()
    result = apply_action(ctx, _action("attack_byzantine", {"n_equivocations": 0}))
    assert not result.success
    assert result.error is not None
    assert result.error["code"] == "bad_payload"


def test_attack_dp_recon_failure_on_bad_payload() -> None:
    ctx, _ = _build_context()
    result = apply_action(
        ctx,
        _action("attack_dp_recon", {"target_agent": "not-an-int", "query_log": []}),
    )
    assert not result.success
    assert result.error is not None
    assert result.error["code"] == "bad_payload"


def test_attack_linkability_failure_on_empty_feature_set() -> None:
    ctx, _ = _build_context()
    result = apply_action(
        ctx,
        _action("attack_linkability", {"feature_set": [], "target_agent": 0}),
    )
    assert not result.success
    assert result.error is not None
    assert result.error["code"] == "bad_payload"


def test_attack_membership_failure_on_empty_observation() -> None:
    ctx, _ = _build_context()
    result = apply_action(ctx, _action("attack_membership", {"target_observation": []}))
    assert not result.success
    assert result.error is not None
    assert result.error["code"] == "bad_payload"


def test_attack_snark_forge_failure_on_missing_circuit() -> None:
    ctx, _ = _build_context()
    result = apply_action(ctx, _action("attack_snark_forge", {}))
    assert not result.success
    assert result.error is not None
    assert result.error["code"] == "bad_payload"


# ── Cross-cutting ──────────────────────────────────────────────────


def test_every_attack_kind_handler_exists() -> None:
    """Sanity: the catalogue advertised by ATTACK_KINDS must dispatch."""
    ctx, _ = _build_context(with_bus=False)
    for kind in ATTACK_KINDS:
        result = apply_action(ctx, _action(kind, {"bad": True}))
        # Every kind should resolve to a handler (not "unknown_kind").
        assert result.error is None or result.error.get("code") != "unknown_kind", kind


def test_attacks_without_bus_do_not_crash() -> None:
    """Attacks must degrade gracefully when no event bus is attached."""
    ctx, _ = _build_context(with_bus=False)
    result = apply_action(
        ctx,
        _action(
            "attack_replay",
            {"target_signature_hex": "ab" * 8, "replay_offset": 0},
        ),
    )
    assert result.success
