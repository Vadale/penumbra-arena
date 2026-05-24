"""Tier 4 — operator defense actions.

Concept taught: every Tier 4 ``defense_*`` action is a *policy toggle*
on the operator's :class:`DefenseState`. The transport's
``GET /operator/defense_status`` endpoint round-trips the same state
so the dashboard tile and the CLI see one consistent view. Two of the
seven actions also reach outside the state struct:
:func:`_handle_defense_rotate_keys` swaps the operator's Dilithium
keypair (old sigs must stop verifying) and :func:`_handle_defense_enable_krum`
mutates the attached :class:`FederatedTrainer`'s aggregation method.

The tests in this file are 6 x (happy + failure) = 12 plus the cross-
cutting "rotate_keys invalidates old sigs" + "pause_dp blocks query_dp"
regressions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from penumbra_core.arena import ArenaConfig
from penumbra_core.economy import Market, Wallet
from penumbra_core.logistics import LogisticsMempool
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_crypto.dp import DPMechanism, PrivacyBudget
from penumbra_crypto.pq import verify as pq_verify
from penumbra_operator.actions import (
    DEFENSE_KINDS,
    OperatorAction,
    OperatorContext,
    apply_action,
)
from penumbra_transport.agent_signing import AgentKeystore


@dataclass(slots=True)
class _StubTrainer:
    """Minimal FederatedTrainer surface: ``set_method`` + ``krum_f``."""

    aggregation_method: str = "fedavg"
    krum_f: int = 1
    raises_on_set: bool = False

    def set_method(self, method: str) -> None:
        if self.raises_on_set:
            raise ValueError("forced failure")
        self.aggregation_method = method


def _build_context(
    *,
    n_agents: int = 4,
    operator_coins: float = 100.0,
    trainer: _StubTrainer | None = None,
) -> OperatorContext:
    sim = Simulation.build(
        SimulationConfig(n_agents=n_agents, arena=ArenaConfig(n_nodes=15)),
        bootstrap(42),
    )
    from penumbra_core.agent import Agent, random_walk_policy

    operator_id = n_agents
    spawn = int(next(iter(sim.arena.graph.nodes())))
    operator_agent = Agent(id=operator_id, position=spawn, policy=random_walk_policy, home=spawn)
    sim.operator_agent = operator_agent
    market = Market.build(nodes=list(sim.arena.graph.nodes()), n_agents=n_agents, seed=42)
    market.wallets[operator_id] = Wallet(agent_id=operator_id, coins=operator_coins)
    keystore = AgentKeystore.for_n_agents(n_agents + 1)
    return OperatorContext(
        simulation=sim,
        operator_agent=operator_agent,
        operator_agent_id=operator_id,
        market=market,
        mempool=LogisticsMempool(),
        dp_mechanism=DPMechanism(PrivacyBudget(epsilon=10.0)),
        keystore=keystore,
        initial_coins=operator_coins,
        federated_trainer=trainer,
    )


def _action(kind: str, payload: dict[str, Any], *, tick: int = 0) -> OperatorAction:
    return OperatorAction(kind=kind, payload=payload, submit_tick=tick)


# ── Happy paths ────────────────────────────────────────────────────


def test_defense_k_anonymity_happy_updates_state() -> None:
    ctx = _build_context()
    result = apply_action(
        ctx,
        _action("defense_k_anonymity", {"k": 5, "statistic": "money_supply"}),
    )
    assert result.success
    assert ctx.defenses.k_anonymity == {"k": 5, "statistic": "money_supply"}
    assert result.data["effective_k"] == 5


def test_defense_padding_happy_updates_state() -> None:
    ctx = _build_context()
    result = apply_action(
        ctx,
        _action("defense_padding", {"kind": "request", "size": 1024}),
    )
    assert result.success
    assert ctx.defenses.padding == {"kind": "request", "size": 1024}
    assert result.data["padded_size"] == 1024


def test_defense_gan_poison_happy_updates_state() -> None:
    ctx = _build_context()
    result = apply_action(
        ctx,
        _action("defense_gan_poison", {"rate": 0.3, "target_stat": "price_index"}),
    )
    assert result.success
    assert ctx.defenses.gan_poison == {"rate": 0.3, "target_stat": "price_index"}
    assert result.data["rate"] == 0.3


def test_defense_pause_dp_happy_blocks_subsequent_query_dp() -> None:
    ctx = _build_context()
    paused = apply_action(ctx, _action("defense_pause_dp", {}))
    assert paused.success
    assert ctx.defenses.dp_paused is True
    blocked = apply_action(
        ctx,
        _action("query_dp", {"statistic": "money_supply", "epsilon": 0.01}),
    )
    assert not blocked.success
    assert blocked.error is not None
    assert blocked.error["code"] == "dp_paused"
    # Resume + retry succeeds.
    resumed = apply_action(ctx, _action("defense_resume_dp", {}))
    assert resumed.success
    ok = apply_action(
        ctx,
        _action("query_dp", {"statistic": "money_supply", "epsilon": 0.01}),
    )
    assert ok.success


def test_defense_rotate_keys_happy_invalidates_old_signature() -> None:
    ctx = _build_context()
    sign_before = apply_action(ctx, _action("sign", {"message": "deadbeef" * 4}))
    assert sign_before.success
    old_pk_hex = sign_before.data["public_key_hex"]
    old_sig_hex = sign_before.data["signature_hex"]
    # Rotate the operator's keypair.
    rotated = apply_action(ctx, _action("defense_rotate_keys", {}))
    assert rotated.success
    assert rotated.data["rotated"] is True
    assert rotated.data["new_public_key_hex"] != old_pk_hex
    # The new keypair is in place; old sigs verify against the OLD
    # public key (signatures themselves do not change) but they no
    # longer trace back to the operator's CURRENT key, so a verifier
    # using the rotated key MUST reject.
    new_kp = ctx.keystore.keypairs[ctx.operator_agent_id]
    ok_against_new = pq_verify(
        new_kp.public_key, bytes.fromhex("deadbeef" * 4), bytes.fromhex(old_sig_hex)
    )
    assert ok_against_new is False
    assert ctx.defenses.key_rotations == 1


def test_defense_enable_krum_happy_mutates_trainer() -> None:
    trainer = _StubTrainer(aggregation_method="fedavg", krum_f=1)
    ctx = _build_context(trainer=trainer)
    result = apply_action(ctx, _action("defense_enable_krum", {"f": 3}))
    assert result.success
    assert trainer.aggregation_method == "krum"
    assert trainer.krum_f == 3
    assert ctx.defenses.krum_f == 3


# ── Failure paths ──────────────────────────────────────────────────


def test_defense_k_anonymity_failure_on_bad_k() -> None:
    ctx = _build_context()
    result = apply_action(
        ctx,
        _action("defense_k_anonymity", {"k": 0, "statistic": "money_supply"}),
    )
    assert not result.success
    assert result.error is not None
    assert result.error["code"] == "bad_payload"


def test_defense_padding_failure_on_bad_kind() -> None:
    ctx = _build_context()
    result = apply_action(
        ctx,
        _action("defense_padding", {"kind": "rocket", "size": 256}),
    )
    assert not result.success
    assert result.error is not None
    assert result.error["code"] == "bad_payload"


def test_defense_gan_poison_failure_on_bad_rate() -> None:
    ctx = _build_context()
    result = apply_action(
        ctx,
        _action("defense_gan_poison", {"rate": 2.0, "target_stat": "x"}),
    )
    assert not result.success
    assert result.error is not None
    assert result.error["code"] == "bad_payload"


def test_defense_pause_dp_resume_failure_path_via_double_resume() -> None:
    """Resume on a non-paused DP is a no-op success (idempotent)."""
    ctx = _build_context()
    # Resume with nothing paused: still succeeds (idempotent).
    result = apply_action(ctx, _action("defense_resume_dp", {}))
    assert result.success
    # But query_dp with bad payload still fails for the right reason.
    bad = apply_action(ctx, _action("query_dp", {"statistic": "x", "epsilon": -1}))
    assert not bad.success
    assert bad.error is not None
    assert bad.error["code"] in ("bad_payload", "unknown_statistic")


def test_defense_rotate_keys_failure_when_no_keypair() -> None:
    """Empty keystore (no operator keypair) yields no_keypair."""
    ctx = _build_context()
    ctx.keystore.keypairs.clear()
    result = apply_action(ctx, _action("defense_rotate_keys", {}))
    assert not result.success
    assert result.error is not None
    assert result.error["code"] == "no_keypair"


def test_defense_enable_krum_failure_without_trainer() -> None:
    ctx = _build_context(trainer=None)
    result = apply_action(ctx, _action("defense_enable_krum", {"f": 2}))
    assert not result.success
    assert result.error is not None
    assert result.error["code"] == "no_trainer"


# ── Cross-cutting ──────────────────────────────────────────────────


def test_every_defense_kind_has_handler() -> None:
    ctx = _build_context()
    for kind in DEFENSE_KINDS:
        result = apply_action(ctx, _action(kind, {"bad": True}))
        assert result.error is None or result.error.get("code") != "unknown_kind", kind


def test_defense_enable_krum_failure_on_bad_f() -> None:
    trainer = _StubTrainer()
    ctx = _build_context(trainer=trainer)
    result = apply_action(ctx, _action("defense_enable_krum", {"f": -1}))
    assert not result.success
    assert result.error is not None
    assert result.error["code"] == "bad_payload"
