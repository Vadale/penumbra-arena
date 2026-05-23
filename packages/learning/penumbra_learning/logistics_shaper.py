"""Logistics-aware reward shaping for MAPPO carriers.

Concept taught: how to align a learned multi-agent policy with the
KPIs that matter to a supply-chain operator. The base MAPPO reward
optimises for reaching match goals; the shaper adds three signals
the env didn't expose by default:

- per-agent **dispatch bonus** when an order is fulfilled by that
  agent (a carrier-revenue analogue)
- per-agent **dispatch penalty** while an assignment sits idle (a
  holding-cost / SLA-pressure analogue)
- an episode-end **fill-rate bonus** scaled by overall service level
  (a shared-utility credit assignment — all carriers benefit when
  the network as a whole serves end-customer demand)

The shaper is intentionally read-only on the simulation: it never
mutates the mempool, demand model, or market. It snapshots the
state it needs at construction (or via inject_*) and observes
change deltas across ticks.

Spec: LOGISTICS_PLAN.md Tier 4 at repo root.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from penumbra_core.logistics import DemandModel, LogisticsMempool
    from penumbra_core.simulation import Simulation

    from penumbra_learning.env import RewardWeights


class _MempoolLike(Protocol):
    """Subset of LogisticsMempool the shaper relies on.

    ``recent_carrier_rewards`` is the Phase 6a Tier 4 fast-path: a
    bounded deque of ``(agent_id, reward)`` pairs maintained by the
    core ``LogisticsMempool.fulfil``. When the shaper sees it on the
    wired mempool we consume it directly instead of re-scanning the
    fulfilled book — both faster and correct under concurrent
    fulfilment from the live orchestrator + the background trainer's
    env (which can otherwise both observe the same order and double-
    pay it).

    ``Any`` element types keep the Protocol structurally compatible
    with both the real ``LogisticsMempool`` (whose pending / fulfilled
    are typed ``list[Order]`` / ``deque[Order]``) and the lightweight
    test stubs that use ``list[Any]`` — Python's nominal mutability
    rules make ``list[X]`` invariant in ``X`` and would otherwise
    reject every concrete instance.
    """

    pending: list[Any]
    fulfilled: list[Any]


@dataclass(slots=True)
class LogisticsRewardShaper:
    """Compute per-agent logistics shaping rewards on every env step.

    The shaper accepts an explicit mempool + demand model (typical
    test setup) or, if neither is provided at construction, it tries
    to discover them on the wrapped simulation at step-time. Both
    discovery paths fail gracefully — when no orchestrator state is
    available the shaper simply returns zeros, leaving the base MAPPO
    reward untouched.
    """

    mempool: _MempoolLike | None = None
    demand: object | None = None
    _seen_fulfilled_ids: set[int] = field(default_factory=set)
    _assignment_first_seen: dict[int, int] = field(default_factory=dict)
    # order_id -> tick at which we first observed the assignment
    _tick: int = 0
    _last_terminal_bonus_applied: bool = False
    _carrier_rewards_consumed: int = 0
    # Total count of entries the shaper has paid out from the
    # mempool's recent_carrier_rewards deque. The mempool's append-
    # only counter only grows; even if the deque trims old entries
    # on the left, the rightmost N items (where N = len(deque)) are
    # always the newest, so we credit those if they weren't yet seen.

    def reset(self) -> None:
        """Clear shaper state — called when the env resets.

        The carrier-rewards consumed counter is intentionally NOT
        reset: it tracks the position on the LIVE mempool's monotonic
        counter (which doesn't restart on env.reset), so resetting it
        would re-credit historical fulfilments on the next step.
        """
        self._seen_fulfilled_ids.clear()
        self._assignment_first_seen.clear()
        self._tick = 0
        self._last_terminal_bonus_applied = False

    def inject(
        self,
        *,
        mempool: LogisticsMempool | None = None,
        demand: DemandModel | None = None,
    ) -> None:
        """Wire the shaper to a live orchestrator's mempool + demand model."""
        if mempool is not None:
            self.mempool = mempool  # type: ignore[assignment]
        if demand is not None:
            self.demand = demand

    def step(
        self,
        *,
        sim: Simulation,
        possible_agents: list[str],
        is_terminal: bool,
        weights: RewardWeights,
    ) -> dict[str, float]:
        """Compute the per-agent logistics reward contribution for this tick.

        Returns a dict keyed by the env's `possible_agents` IDs; agents
        with no contribution are present with 0.0 so callers can sum
        without `KeyError`.
        """
        rewards: dict[str, float] = dict.fromkeys(possible_agents, 0.0)

        mempool = self._resolve_mempool(sim)
        demand = self._resolve_demand(sim)

        if mempool is None and demand is None:
            return rewards

        self._tick += 1

        if mempool is not None:
            self._apply_dispatch_bonus(mempool, possible_agents, weights, rewards)
            self._apply_dispatch_penalty(mempool, possible_agents, weights, rewards)

        if is_terminal and demand is not None and not self._last_terminal_bonus_applied:
            self._apply_fill_rate_bonus(demand, possible_agents, weights, rewards)
            self._last_terminal_bonus_applied = True

        return rewards

    # ── internals ────────────────────────────────────────────────────

    def _resolve_mempool(self, sim: Simulation) -> _MempoolLike | None:
        if self.mempool is not None:
            return self.mempool
        return getattr(sim, "logistics_mempool", None)

    def _resolve_demand(self, sim: Simulation) -> object | None:
        if self.demand is not None:
            return self.demand
        return getattr(sim, "demand", None)

    def _apply_dispatch_bonus(
        self,
        mempool: _MempoolLike,
        possible_agents: list[str],
        weights: RewardWeights,
        rewards: dict[str, float],
    ) -> None:
        # Fast path (Phase 6a Tier 4): the mempool keeps a bounded
        # ``recent_carrier_rewards`` deque plus a monotonic
        # ``total_carrier_fulfilments`` counter so we can drain only
        # the newest entries since the last call WITHOUT re-scanning
        # the whole ``fulfilled`` book. Falls back to the legacy walk
        # when the mempool stub (used by some tests) lacks the deque.
        recent = getattr(mempool, "recent_carrier_rewards", None)
        total = getattr(mempool, "total_carrier_fulfilments", None)
        if recent is not None and total is not None:
            n_new = max(0, int(total) - self._carrier_rewards_consumed)
            n_in_deque = len(recent)
            n_take = min(n_new, n_in_deque)
            self._carrier_rewards_consumed = int(total)
            if weights.logistics_dispatch_bonus == 0.0 or n_take == 0:
                return
            bonus = float(weights.logistics_dispatch_bonus)
            # Take the rightmost n_take entries (the newest ones).
            tail = list(recent)[-n_take:]
            for agent_id, _reward in tail:
                if agent_id < 0:
                    continue
                agent_key = f"agent_{int(agent_id)}"
                if agent_key in rewards:
                    rewards[agent_key] += bonus
            return
        # Legacy slow path: walk the fulfilled list and dedup by order id.
        if weights.logistics_dispatch_bonus == 0.0:
            for order in mempool.fulfilled:
                self._seen_fulfilled_ids.add(_order_id(order))
            return
        bonus = float(weights.logistics_dispatch_bonus)
        for order in mempool.fulfilled:
            oid = _order_id(order)
            if oid in self._seen_fulfilled_ids:
                continue
            self._seen_fulfilled_ids.add(oid)
            carrier = _order_fulfilled_by(order)
            if carrier is None or carrier < 0:
                continue
            agent_key = f"agent_{int(carrier)}"
            if agent_key in rewards:
                rewards[agent_key] += bonus

    def _apply_dispatch_penalty(
        self,
        mempool: _MempoolLike,
        possible_agents: list[str],
        weights: RewardWeights,
        rewards: dict[str, float],
    ) -> None:
        # Always update the assignment first-seen map; the penalty value
        # only changes per-tick credit application.
        active_assignments: set[int] = set()
        penalty = float(weights.logistics_dispatch_penalty)
        for order in mempool.pending:
            assigned_to = _order_assigned_to(order)
            if assigned_to is None or assigned_to < 0:
                continue
            oid = _order_id(order)
            active_assignments.add(oid)
            if oid not in self._assignment_first_seen:
                self._assignment_first_seen[oid] = self._tick
                continue  # first tick we see the assignment — no stale penalty yet
            if penalty == 0.0:
                continue
            agent_key = f"agent_{int(assigned_to)}"
            if agent_key in rewards:
                rewards[agent_key] -= penalty
        # Drop assignments that disappeared (fulfilled or reassigned).
        for stale in set(self._assignment_first_seen) - active_assignments:
            del self._assignment_first_seen[stale]

    def _apply_fill_rate_bonus(
        self,
        demand: object,
        possible_agents: list[str],
        weights: RewardWeights,
        rewards: dict[str, float],
    ) -> None:
        bonus = float(weights.fill_rate_bonus)
        if bonus == 0.0:
            return
        served = float(getattr(demand, "cumulative_served", 0))
        requested = float(getattr(demand, "cumulative_requested", 0))
        if requested <= 0:
            return
        fill_rate = served / requested
        share = bonus * fill_rate
        for agent_key in possible_agents:
            rewards[agent_key] += share


def _order_id(order: object) -> int:
    """Read `Order.id` defensively for tests using lightweight stubs."""
    return int(order.id)  # type: ignore[attr-defined]


def _order_fulfilled_by(order: object) -> int | None:
    val = getattr(order, "fulfilled_by", None)
    return None if val is None else int(val)


def _order_assigned_to(order: object) -> int | None:
    val = getattr(order, "assigned_to", None)
    return None if val is None else int(val)


__all__ = ["LogisticsRewardShaper"]
