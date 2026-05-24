"""Operator action catalogue + dispatch.

Concept taught: every operator-visible primitive (move / buy / sell /
dispatch / cancel / DP query / sign / verify) is a small *handler*
that takes an :class:`OperatorContext` + a payload and returns an
:class:`OperatorActionResult`. The handler validates server-side
(insufficient coins, no path, ε exhausted, unknown order) and
surfaces structured error info instead of raising — the queue drain
keeps going even if one action is bad.

A 50 ms time-budget is enforced per action: a handler that runs over
its budget gets its result tagged ``skipped=True`` so the operator
can see the action was dropped without the loop stalling.

Tier 1 catalogue (8 actions):

| kind                | payload                                       |
|---------------------|-----------------------------------------------|
| ``move``            | ``{target_node: int}``                        |
| ``buy``             | ``{product: int, qty: int}``                  |
| ``sell``            | ``{product: int, qty: int}``                  |
| ``dispatch_order``  | ``{city, product, qty, reward}``              |
| ``cancel_assignment`` | ``{order_id: int}``                          |
| ``query_dp``        | ``{statistic: str, epsilon: float}``          |
| ``sign``            | ``{message: bytes}``                          |
| ``verify``          | ``{message, sig, public_key}``                |
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from penumbra_core.agent import Agent
    from penumbra_core.economy import Market
    from penumbra_core.logistics import LogisticsMempool
    from penumbra_core.simulation import Simulation
    from penumbra_crypto.dp import DPMechanism
    from penumbra_transport.agent_signing import AgentKeystore
    from penumbra_transport.events import EventBus

ACTION_TIME_BUDGET_S: float = 0.050


@dataclass(slots=True)
class DefenseState:
    """Mutable record of which Tier 4 defenses are active for the operator.

    Tier 4 defenses are *operator-scoped policy toggles*: the operator
    flips them via the corresponding ``defense_*`` action, the state
    lives on the :class:`OperatorContext`, and the rest of the system
    reads from this struct (e.g. ``_handle_query_dp`` checks
    ``dp_paused`` before consuming any ε). Storing the policy here keeps
    the orchestrator out of the per-action hot path.
    """

    k_anonymity: dict[str, Any] | None = None
    padding: dict[str, Any] | None = None
    gan_poison: dict[str, Any] | None = None
    dp_paused: bool = False
    krum_f: int | None = None
    key_rotations: int = 0


class OperatorActionError(Exception):
    """Base class for operator action failures.

    Handlers never raise this directly into the queue drain — they
    return an :class:`OperatorActionResult` with ``success=False``
    and a structured ``error`` mapping. The exception type exists so
    transport endpoints can also surface validation failures as 400s
    when an action is rejected at submission time (e.g. unknown
    ``kind``).
    """


@dataclass(slots=True)
class OperatorAction:
    """One queued operator command.

    ``submit_tick`` is the tick at which the action was enqueued;
    ``target_tick`` (when set) defers the action until that simulation
    tick. The queue's deterministic ordering is
    ``(submit_tick, insertion_sequence)``.
    """

    kind: str
    payload: dict[str, Any]
    submit_tick: int
    target_tick: int | None = None


@dataclass(slots=True)
class OperatorActionResult:
    """Structured outcome of one applied action.

    ``data`` is the action-specific success payload (e.g. the noised
    statistic for ``query_dp`` or the order id for ``dispatch_order``);
    ``error`` is set when ``success=False`` (with ``code`` + ``message``).
    ``skipped=True`` flags an action that hit the 50 ms time budget.
    ``elapsed_ms`` is the wall-clock cost of the handler (useful for
    the dashboard and for the per-action budget contract).
    """

    kind: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: dict[str, str] | None = None
    skipped: bool = False
    elapsed_ms: float = 0.0
    applied_tick: int = -1


@dataclass(slots=True)
class OperatorContext:
    """Bundle of references the handlers need to mutate sim state.

    ``initial_coins`` is the wallet amount the operator gets when
    enabled; it's preserved here so :func:`refresh_wallet` can restore
    it on re-enable.
    """

    simulation: Simulation
    operator_agent: Agent
    operator_agent_id: int
    market: Market
    mempool: LogisticsMempool
    dp_mechanism: DPMechanism
    keystore: AgentKeystore
    initial_coins: float = 100.0
    event_bus: EventBus | None = None
    federated_trainer: object | None = None
    defenses: DefenseState = field(default_factory=DefenseState)

    @property
    def current_tick(self) -> int:
        """Convenience accessor for the live tick counter."""
        return int(self.simulation.tick_counter)


# ── handlers ───────────────────────────────────────────────────────


def _ok(kind: str, data: dict[str, Any], *, tick: int) -> OperatorActionResult:
    return OperatorActionResult(kind=kind, success=True, data=data, applied_tick=tick)


def _err(
    kind: str, code: str, message: str, *, tick: int, data: dict[str, Any] | None = None
) -> OperatorActionResult:
    return OperatorActionResult(
        kind=kind,
        success=False,
        data=data or {},
        error={"code": code, "message": message},
        applied_tick=tick,
    )


def _handle_move(ctx: OperatorContext, payload: dict[str, Any]) -> OperatorActionResult:
    tick = ctx.current_tick
    target = payload.get("target_node")
    if not isinstance(target, int):
        return _err("move", "bad_payload", "target_node must be int", tick=tick)
    arena = ctx.simulation.arena
    if target not in arena.graph.nodes():
        return _err("move", "unknown_node", f"node {target} not in arena", tick=tick)
    if target == ctx.operator_agent.position:
        return _ok(
            "move",
            {
                "target_node": int(target),
                "from_node": int(ctx.operator_agent.position),
                "cost": 0.0,
                "noop": True,
            },
            tick=tick,
        )
    neighbours = arena.neighbours(ctx.operator_agent.position)
    if target not in neighbours:
        return _err(
            "move",
            "no_path",
            f"node {target} is not a neighbour of {ctx.operator_agent.position}",
            tick=tick,
        )
    cost = float(arena.cost_of(ctx.operator_agent.position, target))
    wallet = ctx.market.wallets.get(ctx.operator_agent_id)
    if wallet is None:
        return _err("move", "no_wallet", "operator wallet missing", tick=tick)
    if wallet.coins < cost:
        return _err(
            "move",
            "insufficient_coins",
            f"need {cost} coins to move, have {wallet.coins}",
            tick=tick,
        )
    from_node = int(ctx.operator_agent.position)
    wallet.coins -= cost
    ctx.operator_agent.move_to(int(target), cost, tick=tick)
    return _ok(
        "move",
        {
            "from_node": from_node,
            "target_node": int(target),
            "cost": cost,
            "coins_after": float(wallet.coins),
        },
        tick=tick,
    )


def _handle_buy(ctx: OperatorContext, payload: dict[str, Any]) -> OperatorActionResult:
    tick = ctx.current_tick
    product = payload.get("product")
    qty = payload.get("qty")
    if not isinstance(product, int) or not isinstance(qty, int) or qty <= 0:
        return _err("buy", "bad_payload", "product:int and qty:int>0 required", tick=tick)
    ms = ctx.market.markets.get(int(ctx.operator_agent.position))
    if ms is None:
        return _err(
            "buy",
            "no_market",
            f"no market at node {ctx.operator_agent.position}",
            tick=tick,
        )
    if product not in ms.stocked_products:
        return _err(
            "buy",
            "unstocked",
            f"product {product} not stocked at node {ms.node_id}",
            tick=tick,
        )
    wallet = ctx.market.wallets.get(ctx.operator_agent_id)
    if wallet is None:
        return _err("buy", "no_wallet", "operator wallet missing", tick=tick)
    avail = ms.inventory.get(product, 0)
    if avail < qty:
        return _err(
            "buy",
            "insufficient_inventory",
            f"city has {avail}, requested {qty}",
            tick=tick,
        )
    ask = ms.ask_price.get(product, 0.0)
    cost = ask * qty
    if wallet.coins < cost:
        return _err(
            "buy",
            "insufficient_coins",
            f"need {cost} coins, have {wallet.coins}",
            tick=tick,
        )
    wallet.coins -= cost
    wallet.inventory[product] = wallet.inventory.get(product, 0) + qty
    ms.inventory[product] = avail - qty
    ms.treasury += cost
    return _ok(
        "buy",
        {
            "product": int(product),
            "qty": int(qty),
            "unit_price": float(ask),
            "total_cost": float(cost),
            "coins_after": float(wallet.coins),
            "inventory_after": int(wallet.inventory.get(product, 0)),
        },
        tick=tick,
    )


def _handle_sell(ctx: OperatorContext, payload: dict[str, Any]) -> OperatorActionResult:
    tick = ctx.current_tick
    product = payload.get("product")
    qty = payload.get("qty")
    if not isinstance(product, int) or not isinstance(qty, int) or qty <= 0:
        return _err("sell", "bad_payload", "product:int and qty:int>0 required", tick=tick)
    ms = ctx.market.markets.get(int(ctx.operator_agent.position))
    if ms is None:
        return _err(
            "sell",
            "no_market",
            f"no market at node {ctx.operator_agent.position}",
            tick=tick,
        )
    if product not in ms.stocked_products:
        return _err(
            "sell",
            "unstocked",
            f"city {ms.node_id} doesn't buy product {product}",
            tick=tick,
        )
    wallet = ctx.market.wallets.get(ctx.operator_agent_id)
    if wallet is None:
        return _err("sell", "no_wallet", "operator wallet missing", tick=tick)
    owned = wallet.inventory.get(product, 0)
    if owned < qty:
        return _err(
            "sell",
            "insufficient_inventory",
            f"agent has {owned}, requested {qty}",
            tick=tick,
        )
    ask = ms.ask_price.get(product, 0.0)
    # Match the Market's bid/ask spread (85% of ask).
    bid = ask * 0.85
    revenue = bid * qty
    if ms.treasury < revenue:
        return _err(
            "sell",
            "insufficient_treasury",
            f"city has {ms.treasury} coins, owes {revenue}",
            tick=tick,
        )
    wallet.inventory[product] = owned - qty
    if wallet.inventory[product] == 0:
        del wallet.inventory[product]
    wallet.coins += revenue
    ms.treasury -= revenue
    ms.inventory[product] = min(ms.max_inventory, ms.inventory.get(product, 0) + qty)
    return _ok(
        "sell",
        {
            "product": int(product),
            "qty": int(qty),
            "unit_price": float(bid),
            "total_revenue": float(revenue),
            "coins_after": float(wallet.coins),
            "inventory_after": int(wallet.inventory.get(product, 0)),
        },
        tick=tick,
    )


def _handle_dispatch_order(ctx: OperatorContext, payload: dict[str, Any]) -> OperatorActionResult:
    tick = ctx.current_tick
    city = payload.get("city")
    product = payload.get("product")
    qty = payload.get("qty")
    reward = payload.get("reward")
    if not (
        isinstance(city, int)
        and isinstance(product, int)
        and isinstance(qty, int)
        and isinstance(reward, (int, float))
    ):
        return _err(
            "dispatch_order",
            "bad_payload",
            "city:int, product:int, qty:int, reward:number required",
            tick=tick,
        )
    if qty <= 0 or reward < 0:
        return _err(
            "dispatch_order",
            "bad_payload",
            "qty must be > 0 and reward >= 0",
            tick=tick,
        )
    if city not in ctx.market.markets:
        return _err(
            "dispatch_order",
            "unknown_city",
            f"city {city} not in market",
            tick=tick,
        )
    order = ctx.mempool.place(
        city=int(city),
        product=int(product),
        quantity=int(qty),
        tick=tick,
        reward=float(reward),
        assigned_to=ctx.operator_agent_id,
    )
    return _ok(
        "dispatch_order",
        {
            "order_id": int(order.id),
            "city": int(order.city),
            "product": int(order.product),
            "qty": int(order.quantity),
            "reward": float(order.reward),
            "assigned_to": int(ctx.operator_agent_id),
        },
        tick=tick,
    )


def _handle_cancel_assignment(
    ctx: OperatorContext, payload: dict[str, Any]
) -> OperatorActionResult:
    tick = ctx.current_tick
    order_id = payload.get("order_id")
    if not isinstance(order_id, int):
        return _err(
            "cancel_assignment",
            "bad_payload",
            "order_id:int required",
            tick=tick,
        )
    for order in ctx.mempool.pending:
        if order.id == order_id:
            if order.assigned_to != ctx.operator_agent_id:
                return _err(
                    "cancel_assignment",
                    "not_owner",
                    f"order {order_id} is assigned to {order.assigned_to}",
                    tick=tick,
                )
            order.assigned_to = None
            order.assigned_tick = None
            return _ok(
                "cancel_assignment",
                {"order_id": int(order_id), "released": True},
                tick=tick,
            )
    return _err(
        "cancel_assignment",
        "unknown_order",
        f"no pending order with id {order_id}",
        tick=tick,
    )


_DP_STATISTICS: dict[str, Callable[[OperatorContext], tuple[float, float]]] = {
    # statistic -> (current_value, sensitivity)
    "money_supply": lambda ctx: (float(ctx.market.money_supply()), 1.0),
    "price_index": lambda ctx: (float(ctx.market.price_index()), 1.0),
    "n_pending_orders": lambda ctx: (float(len(ctx.mempool.pending)), 1.0),
    "operator_coins": lambda ctx: (
        float(ctx.market.wallets[ctx.operator_agent_id].coins),
        1.0,
    ),
}


def _handle_query_dp(ctx: OperatorContext, payload: dict[str, Any]) -> OperatorActionResult:
    tick = ctx.current_tick
    if ctx.defenses.dp_paused:
        return _err(
            "query_dp",
            "dp_paused",
            "DP queries are paused; POST /operator/defense_resume_dp to resume",
            tick=tick,
        )
    stat = payload.get("statistic")
    epsilon = payload.get("epsilon")
    if not isinstance(stat, str) or not isinstance(epsilon, (int, float)) or epsilon <= 0:
        return _err(
            "query_dp",
            "bad_payload",
            "statistic:str and epsilon:float>0 required",
            tick=tick,
        )
    if stat not in _DP_STATISTICS:
        return _err(
            "query_dp",
            "unknown_statistic",
            f"unknown statistic {stat!r}; choose from {sorted(_DP_STATISTICS)}",
            tick=tick,
        )
    value, sensitivity = _DP_STATISTICS[stat](ctx)
    try:
        noised = ctx.dp_mechanism.laplace(value, sensitivity=sensitivity, epsilon=float(epsilon))
    except Exception as exc:  # pragma: no cover - exact branch covered by failure test
        return _err(
            "query_dp",
            "budget_exhausted",
            str(exc),
            tick=tick,
            data={
                "statistic": stat,
                "epsilon_requested": float(epsilon),
                "epsilon_remaining": float(ctx.dp_mechanism.budget.remaining_epsilon),
            },
        )
    return _ok(
        "query_dp",
        {
            "statistic": stat,
            "epsilon": float(epsilon),
            "noised_value": float(noised),
            "epsilon_spent": float(ctx.dp_mechanism.budget.epsilon_spent),
            "epsilon_remaining": float(ctx.dp_mechanism.budget.remaining_epsilon),
        },
        tick=tick,
    )


def _handle_sign(ctx: OperatorContext, payload: dict[str, Any]) -> OperatorActionResult:
    tick = ctx.current_tick
    message = payload.get("message")
    if isinstance(message, str):
        try:
            message_bytes = bytes.fromhex(message)
        except ValueError:
            return _err("sign", "bad_payload", "message hex decode failed", tick=tick)
    elif isinstance(message, (bytes, bytearray)):
        message_bytes = bytes(message)
    else:
        return _err("sign", "bad_payload", "message must be hex string or bytes", tick=tick)
    if not message_bytes:
        return _err("sign", "bad_payload", "message must be non-empty", tick=tick)
    if ctx.operator_agent_id >= len(ctx.keystore.keypairs):
        return _err("sign", "no_keypair", "operator keypair missing", tick=tick)
    from penumbra_crypto.pq import sign as _sig_sign

    kp = ctx.keystore.keypairs[ctx.operator_agent_id]
    sig = _sig_sign(kp.secret_key, message_bytes)
    return _ok(
        "sign",
        {
            "message_hex": message_bytes.hex(),
            "signature_hex": sig.hex(),
            "public_key_hex": kp.public_key.hex(),
            "signature_size": len(sig),
        },
        tick=tick,
    )


def _handle_verify(ctx: OperatorContext, payload: dict[str, Any]) -> OperatorActionResult:
    tick = ctx.current_tick
    message = payload.get("message")
    sig = payload.get("sig")
    public_key = payload.get("public_key")

    def _to_bytes(value: object, name: str) -> bytes | OperatorActionResult:
        if isinstance(value, str):
            try:
                return bytes.fromhex(value)
            except ValueError:
                return _err("verify", "bad_payload", f"{name} hex decode failed", tick=tick)
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        return _err("verify", "bad_payload", f"{name} must be hex or bytes", tick=tick)

    message_bytes = _to_bytes(message, "message")
    if isinstance(message_bytes, OperatorActionResult):
        return message_bytes
    sig_bytes = _to_bytes(sig, "sig")
    if isinstance(sig_bytes, OperatorActionResult):
        return sig_bytes
    pk_bytes = _to_bytes(public_key, "public_key")
    if isinstance(pk_bytes, OperatorActionResult):
        return pk_bytes
    from penumbra_crypto.pq import verify as _sig_verify

    ok = bool(_sig_verify(pk_bytes, message_bytes, sig_bytes))
    return _ok(
        "verify",
        {
            "verified": ok,
            "message_hex": message_bytes.hex(),
            "signature_size": len(sig_bytes),
            "public_key_size": len(pk_bytes),
        },
        tick=tick,
    )


# ── Tier 3: attack actions ────────────────────────────────────────


def _emit_attack_event(
    ctx: OperatorContext,
    kind: str,
    *,
    target: object,
    accepted: bool,
    evidence: dict[str, Any] | None = None,
) -> None:
    """Push an ``operator.attack`` event onto the orchestrator's bus.

    The dashboard event log + any simulated victim handlers subscribe
    to this kind; the per-attack ``kind`` (e.g. ``attack_replay``) is
    inside ``payload['kind']`` so subscribers can dispatch.
    """
    bus = ctx.event_bus
    if bus is None:
        return
    try:
        from penumbra_transport.events import Event
    except ImportError:  # pragma: no cover - transport always shipped
        return
    payload: dict[str, object] = {
        "kind": kind,
        "target": target,
        "accepted": bool(accepted),
    }
    if evidence is not None:
        payload["evidence"] = evidence
    bus.emit(Event(kind="operator.attack", tick=ctx.current_tick, payload=payload))


def _attack_result(
    kind: str,
    *,
    accepted: bool,
    evidence: dict[str, Any],
    defender_response: str,
    tick: int,
) -> OperatorActionResult:
    """Standard envelope: every Tier 3 attack returns the same shape."""
    return _ok(
        kind,
        {
            "accepted": bool(accepted),
            "evidence": dict(evidence),
            "defender_response": str(defender_response),
        },
        tick=tick,
    )


def _handle_attack_replay(ctx: OperatorContext, payload: dict[str, Any]) -> OperatorActionResult:
    tick = ctx.current_tick
    target_sig = payload.get("target_signature_hex")
    offset = payload.get("replay_offset", 0)
    if not isinstance(target_sig, str) or not isinstance(offset, int):
        return _err(
            "attack_replay",
            "bad_payload",
            "target_signature_hex:str and replay_offset:int required",
            tick=tick,
        )
    try:
        bytes.fromhex(target_sig)
    except ValueError:
        return _err("attack_replay", "bad_payload", "target_signature_hex must be hex", tick=tick)
    from penumbra_attacker.attacks import replay

    demo = replay.demo()
    # The replay attack succeeds against the naive protocol only; the
    # tick-binding defence rejects the replay.
    accepted = bool(demo.naive_succeeded) and not bool(demo.with_tick_counter_succeeded)
    evidence: dict[str, Any] = {
        "naive_succeeded": bool(demo.naive_succeeded),
        "with_tick_counter_succeeded": bool(demo.with_tick_counter_succeeded),
        "target_signature_hex": target_sig,
        "replay_offset": int(offset),
    }
    defender_response = (
        "Penumbra binds (tick, agent_id) into the signed message; "
        "the replayed signature is rejected at the next verify call."
    )
    _emit_attack_event(
        ctx, "attack_replay", target=target_sig, accepted=accepted, evidence=evidence
    )
    return _attack_result(
        "attack_replay",
        accepted=accepted,
        evidence=evidence,
        defender_response=defender_response,
        tick=tick,
    )


def _handle_attack_byzantine(ctx: OperatorContext, payload: dict[str, Any]) -> OperatorActionResult:
    tick = ctx.current_tick
    n_eq = payload.get("n_equivocations")
    if not isinstance(n_eq, int) or n_eq <= 0:
        return _err(
            "attack_byzantine",
            "bad_payload",
            "n_equivocations:int>0 required",
            tick=tick,
        )
    from penumbra_attacker.attacks import byzantine

    demo = byzantine.demo()
    accepted = bool(demo.equivocation_detected)
    evidence: dict[str, Any] = {
        "n_equivocations": int(n_eq),
        "equivocation_detected": bool(demo.equivocation_detected),
        "block_a_signed": bool(demo.block_a_signed),
        "block_b_signed": bool(demo.block_b_signed),
    }
    defender_response = (
        "Equivocation proofs (sig_a, block_a, sig_b, block_b) are publicly "
        "verifiable and would slash the validator's stake on a PoS chain."
    )
    _emit_attack_event(
        ctx, "attack_byzantine", target="validator", accepted=accepted, evidence=evidence
    )
    return _attack_result(
        "attack_byzantine",
        accepted=accepted,
        evidence=evidence,
        defender_response=defender_response,
        tick=tick,
    )


def _handle_attack_dp_recon(ctx: OperatorContext, payload: dict[str, Any]) -> OperatorActionResult:
    tick = ctx.current_tick
    target = payload.get("target_agent")
    query_log = payload.get("query_log")
    if not isinstance(target, int) or not isinstance(query_log, list):
        return _err(
            "attack_dp_recon",
            "bad_payload",
            "target_agent:int and query_log:list required",
            tick=tick,
        )
    from penumbra_attacker.attacks import dp_reconstruction

    n_queries = max(8, len(query_log))
    demo = dp_reconstruction.demo(n_bits=16, n_queries=n_queries, noise_scale=0.1)
    accepted = demo.recovered_bit_accuracy > 0.75
    evidence: dict[str, Any] = {
        "target_agent": int(target),
        "n_queries_used": int(demo.n_queries),
        "recovered_bit_accuracy": float(demo.recovered_bit_accuracy),
    }
    defender_response = (
        "The DP accountant caps total ε; once exhausted, no further releases. "
        "Dinur-Nissim needs n^Ω(1) queries — the budget kills the attack."
    )
    _emit_attack_event(
        ctx, "attack_dp_recon", target=int(target), accepted=accepted, evidence=evidence
    )
    return _attack_result(
        "attack_dp_recon",
        accepted=accepted,
        evidence=evidence,
        defender_response=defender_response,
        tick=tick,
    )


def _handle_attack_linkability(
    ctx: OperatorContext, payload: dict[str, Any]
) -> OperatorActionResult:
    tick = ctx.current_tick
    feature_set = payload.get("feature_set")
    target = payload.get("target_agent")
    if not isinstance(feature_set, list) or not isinstance(target, int):
        return _err(
            "attack_linkability",
            "bad_payload",
            "feature_set:list and target_agent:int required",
            tick=tick,
        )
    if not feature_set:
        return _err(
            "attack_linkability",
            "bad_payload",
            "feature_set must be non-empty",
            tick=tick,
        )
    from penumbra_attacker.attacks import linkability

    demo = linkability.demo(n_agents=5, n_matches=10)
    accepted = demo.naive_accuracy > 0.5
    evidence: dict[str, Any] = {
        "target_agent": int(target),
        "feature_set": list(feature_set),
        "naive_accuracy": float(demo.naive_accuracy),
        "with_noise_accuracy": float(demo.with_noise_accuracy),
    }
    defender_response = (
        "Identity-shuffling + Laplace noise on per-match aggregates drops "
        "the matcher to 1/N. See defenses.k_anonymity + gan_defenses."
    )
    _emit_attack_event(
        ctx, "attack_linkability", target=int(target), accepted=accepted, evidence=evidence
    )
    return _attack_result(
        "attack_linkability",
        accepted=accepted,
        evidence=evidence,
        defender_response=defender_response,
        tick=tick,
    )


def _handle_attack_membership(
    ctx: OperatorContext, payload: dict[str, Any]
) -> OperatorActionResult:
    tick = ctx.current_tick
    target_obs = payload.get("target_observation")
    if not isinstance(target_obs, list) or not target_obs:
        return _err(
            "attack_membership",
            "bad_payload",
            "target_observation:list[float] required",
            tick=tick,
        )
    if not all(isinstance(v, (int, float)) for v in target_obs):
        return _err(
            "attack_membership",
            "bad_payload",
            "target_observation entries must be numeric",
            tick=tick,
        )
    from penumbra_attacker.attacks import membership_inference

    demo = membership_inference.demo(n_shadows=3, seed=42)
    accepted = bool(demo.get("success", False))
    accuracy_raw = demo.get("membership_accuracy", 0.0)
    advantage_raw = demo.get("advantage_over_chance", 0.0)
    accuracy = float(accuracy_raw) if isinstance(accuracy_raw, (int, float)) else 0.0
    advantage = float(advantage_raw) if isinstance(advantage_raw, (int, float)) else 0.0
    evidence: dict[str, Any] = {
        "n_features": len(target_obs),
        "membership_accuracy": accuracy,
        "advantage_over_chance": advantage,
    }
    defender_response = (
        "DP-SGD (ε≈1.0) on the MAPPO actor + output-confidence clipping "
        "drops the attack advantage below 1%."
    )
    _emit_attack_event(
        ctx, "attack_membership", target="mappo_policy", accepted=accepted, evidence=evidence
    )
    return _attack_result(
        "attack_membership",
        accepted=accepted,
        evidence=evidence,
        defender_response=defender_response,
        tick=tick,
    )


def _handle_attack_snark_forge(
    ctx: OperatorContext, payload: dict[str, Any]
) -> OperatorActionResult:
    tick = ctx.current_tick
    circuit = payload.get("circuit")
    if not isinstance(circuit, str) or not circuit:
        return _err(
            "attack_snark_forge",
            "bad_payload",
            "circuit:str required",
            tick=tick,
        )
    from penumbra_attacker.attacks import snark_forgery

    try:
        demo = snark_forgery.demo()
        accepted = bool(demo.random_forge_accepted) or bool(
            demo.replay_with_tampered_inputs_accepted
        )
        evidence: dict[str, Any] = {
            "circuit": circuit,
            "random_forge_accepted": bool(demo.random_forge_accepted),
            "replay_with_tampered_inputs_accepted": bool(demo.replay_with_tampered_inputs_accepted),
            "honest_proof_accepted": bool(demo.honest_proof_accepted),
        }
        defender_response = (
            "Groth16 SOUNDNESS: the pairing check rejects both random "
            "garbage and tampered-public-input replays."
        )
    except FileNotFoundError as exc:
        # Artifacts missing — surface as evidence rather than crashing.
        accepted = False
        evidence = {"circuit": circuit, "artifacts_missing": True, "detail": str(exc)}
        defender_response = (
            "Groth16 artifacts not built in this environment; the forger "
            "has no verifying key to attack."
        )
    _emit_attack_event(
        ctx, "attack_snark_forge", target=circuit, accepted=accepted, evidence=evidence
    )
    return _attack_result(
        "attack_snark_forge",
        accepted=accepted,
        evidence=evidence,
        defender_response=defender_response,
        tick=tick,
    )


# ── Tier 4: defense actions ───────────────────────────────────────


def _handle_defense_k_anonymity(
    ctx: OperatorContext, payload: dict[str, Any]
) -> OperatorActionResult:
    tick = ctx.current_tick
    k = payload.get("k")
    statistic = payload.get("statistic")
    if not isinstance(k, int) or k < 1 or not isinstance(statistic, str) or not statistic:
        return _err(
            "defense_k_anonymity",
            "bad_payload",
            "k:int>=1 and statistic:str required",
            tick=tick,
        )
    ctx.defenses.k_anonymity = {"k": int(k), "statistic": statistic}
    return _ok(
        "defense_k_anonymity",
        {"k": int(k), "statistic": statistic, "effective_k": int(k)},
        tick=tick,
    )


def _handle_defense_padding(ctx: OperatorContext, payload: dict[str, Any]) -> OperatorActionResult:
    tick = ctx.current_tick
    kind = payload.get("kind")
    size = payload.get("size")
    if kind not in ("request", "response") or not isinstance(size, int) or size <= 0:
        return _err(
            "defense_padding",
            "bad_payload",
            "kind in {'request','response'} and size:int>0 required",
            tick=tick,
        )
    ctx.defenses.padding = {"kind": kind, "size": int(size)}
    return _ok(
        "defense_padding",
        {"kind": str(kind), "size": int(size), "padded_size": int(size)},
        tick=tick,
    )


def _handle_defense_gan_poison(
    ctx: OperatorContext, payload: dict[str, Any]
) -> OperatorActionResult:
    tick = ctx.current_tick
    rate = payload.get("rate")
    target_stat = payload.get("target_stat")
    if (
        not isinstance(rate, (int, float))
        or not 0.0 <= float(rate) <= 1.0
        or not isinstance(target_stat, str)
        or not target_stat
    ):
        return _err(
            "defense_gan_poison",
            "bad_payload",
            "rate:float in [0,1] and target_stat:str required",
            tick=tick,
        )
    ctx.defenses.gan_poison = {"rate": float(rate), "target_stat": target_stat}
    return _ok(
        "defense_gan_poison",
        {"rate": float(rate), "target_stat": target_stat},
        tick=tick,
    )


def _handle_defense_pause_dp(ctx: OperatorContext, payload: dict[str, Any]) -> OperatorActionResult:
    tick = ctx.current_tick
    ctx.defenses.dp_paused = True
    return _ok(
        "defense_pause_dp",
        {"dp_paused": True},
        tick=tick,
    )


def _handle_defense_resume_dp(
    ctx: OperatorContext, payload: dict[str, Any]
) -> OperatorActionResult:
    tick = ctx.current_tick
    ctx.defenses.dp_paused = False
    return _ok(
        "defense_resume_dp",
        {"dp_paused": False},
        tick=tick,
    )


def _handle_defense_rotate_keys(
    ctx: OperatorContext, payload: dict[str, Any]
) -> OperatorActionResult:
    tick = ctx.current_tick
    if ctx.operator_agent_id >= len(ctx.keystore.keypairs):
        return _err(
            "defense_rotate_keys",
            "no_keypair",
            "operator keypair missing — POST /operator/enable first",
            tick=tick,
        )
    from penumbra_crypto.pq import sig_keygen

    old_pk = ctx.keystore.keypairs[ctx.operator_agent_id].public_key
    new_kp = sig_keygen()
    ctx.keystore.keypairs[ctx.operator_agent_id] = new_kp
    ctx.defenses.key_rotations += 1
    return _ok(
        "defense_rotate_keys",
        {
            "rotated": True,
            "old_public_key_hex": old_pk.hex(),
            "new_public_key_hex": new_kp.public_key.hex(),
            "rotations_total": int(ctx.defenses.key_rotations),
        },
        tick=tick,
    )


def _handle_defense_enable_krum(
    ctx: OperatorContext, payload: dict[str, Any]
) -> OperatorActionResult:
    tick = ctx.current_tick
    f = payload.get("f")
    if not isinstance(f, int) or f < 0:
        return _err(
            "defense_enable_krum",
            "bad_payload",
            "f:int>=0 required",
            tick=tick,
        )
    trainer = ctx.federated_trainer
    if trainer is None:
        return _err(
            "defense_enable_krum",
            "no_trainer",
            "federated_trainer not attached to the orchestrator",
            tick=tick,
        )
    set_method = getattr(trainer, "set_method", None)
    if set_method is None:
        return _err(
            "defense_enable_krum",
            "unsupported_trainer",
            "trainer has no set_method() — wrong trainer kind",
            tick=tick,
        )
    try:
        set_method("krum")
    except Exception as exc:  # pragma: no cover - defensive
        return _err(
            "defense_enable_krum",
            "set_method_failed",
            str(exc),
            tick=tick,
        )
    try:
        trainer.krum_f = int(f)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - defensive
        return _err(
            "defense_enable_krum",
            "set_f_failed",
            str(exc),
            tick=tick,
        )
    ctx.defenses.krum_f = int(f)
    return _ok(
        "defense_enable_krum",
        {"method": "krum", "f": int(f)},
        tick=tick,
    )


_HANDLERS: dict[str, Callable[[OperatorContext, dict[str, Any]], OperatorActionResult]] = {
    "move": _handle_move,
    "buy": _handle_buy,
    "sell": _handle_sell,
    "dispatch_order": _handle_dispatch_order,
    "cancel_assignment": _handle_cancel_assignment,
    "query_dp": _handle_query_dp,
    "sign": _handle_sign,
    "verify": _handle_verify,
    # Tier 3 — attacks
    "attack_replay": _handle_attack_replay,
    "attack_byzantine": _handle_attack_byzantine,
    "attack_dp_recon": _handle_attack_dp_recon,
    "attack_linkability": _handle_attack_linkability,
    "attack_membership": _handle_attack_membership,
    "attack_snark_forge": _handle_attack_snark_forge,
    # Tier 4 — defenses
    "defense_k_anonymity": _handle_defense_k_anonymity,
    "defense_padding": _handle_defense_padding,
    "defense_gan_poison": _handle_defense_gan_poison,
    "defense_pause_dp": _handle_defense_pause_dp,
    "defense_resume_dp": _handle_defense_resume_dp,
    "defense_rotate_keys": _handle_defense_rotate_keys,
    "defense_enable_krum": _handle_defense_enable_krum,
}


ATTACK_KINDS: tuple[str, ...] = (
    "attack_replay",
    "attack_byzantine",
    "attack_dp_recon",
    "attack_linkability",
    "attack_membership",
    "attack_snark_forge",
)

DEFENSE_KINDS: tuple[str, ...] = (
    "defense_k_anonymity",
    "defense_padding",
    "defense_gan_poison",
    "defense_pause_dp",
    "defense_resume_dp",
    "defense_rotate_keys",
    "defense_enable_krum",
)


def known_kinds() -> tuple[str, ...]:
    """The canonical, sorted list of action kinds (used by validation + UI)."""
    return tuple(sorted(_HANDLERS))


def coalesce_moves(actions: list[OperatorAction]) -> list[OperatorAction]:
    """Drop all but the LAST ``move`` in ``actions``.

    Conflict resolution rule from the plan: when multiple moves land in
    the same tick, the operator's stated *intent* is the last one they
    submitted; the earlier ones are stale.
    """
    last_move_idx = -1
    for i, action in enumerate(actions):
        if action.kind == "move":
            last_move_idx = i
    if last_move_idx == -1:
        return actions
    out: list[OperatorAction] = []
    for i, action in enumerate(actions):
        if action.kind == "move" and i != last_move_idx:
            continue
        out.append(action)
    return out


def apply_action(ctx: OperatorContext, action: OperatorAction) -> OperatorActionResult:
    """Dispatch ``action`` onto its handler with the 50 ms time-budget.

    Handlers themselves never raise; if a handler does throw (a bug
    rather than expected validation failure), we coerce it into a
    structured error so the queue drain keeps going.
    """
    handler = _HANDLERS.get(action.kind)
    if handler is None:
        return OperatorActionResult(
            kind=action.kind,
            success=False,
            error={"code": "unknown_kind", "message": f"unknown action kind {action.kind!r}"},
            applied_tick=ctx.current_tick,
        )
    start = time.perf_counter()
    try:
        result = handler(ctx, action.payload)
    except OperatorActionError as exc:
        result = OperatorActionResult(
            kind=action.kind,
            success=False,
            error={"code": "handler_error", "message": str(exc)},
            applied_tick=ctx.current_tick,
        )
    except Exception as exc:  # pragma: no cover - defensive net
        result = OperatorActionResult(
            kind=action.kind,
            success=False,
            error={"code": "handler_crash", "message": repr(exc)},
            applied_tick=ctx.current_tick,
        )
    elapsed = time.perf_counter() - start
    result.elapsed_ms = elapsed * 1000.0
    if elapsed > ACTION_TIME_BUDGET_S:
        # Over-budget: still record the result for traceability but
        # mark it skipped so the operator knows the action was bumped.
        result.skipped = True
    return result


def refresh_wallet(ctx: OperatorContext) -> None:
    """Reset the operator's wallet to ``ctx.initial_coins`` + empty inventory.

    Used by the transport layer's ``/operator/enable`` handler so a
    re-enable is equivalent to a fresh slot — the plan calls this out
    as the expected behaviour of the lifecycle.
    """
    wallet = ctx.market.wallets.get(ctx.operator_agent_id)
    if wallet is None:
        return
    wallet.coins = float(ctx.initial_coins)
    wallet.inventory = {}


__all__ = [
    "ACTION_TIME_BUDGET_S",
    "ATTACK_KINDS",
    "DEFENSE_KINDS",
    "DefenseState",
    "OperatorAction",
    "OperatorActionError",
    "OperatorActionResult",
    "OperatorContext",
    "apply_action",
    "coalesce_moves",
    "known_kinds",
    "refresh_wallet",
]
