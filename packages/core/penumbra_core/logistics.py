"""Logistics layer on top of the existing market.

Concept taught: how an OR-style supply chain emerges from primitive
nodes + capacity + demand + reorder policies. The existing Market
becomes the physical layer; this module adds the operational layer
(carrier capacity, end-customer demand, reorder triggers, KPIs).

Spec: LOGISTICS_PLAN.md at repo root.

Tier 1 ships: CargoConstraints, DemandModel, Order, LogisticsMempool,
ReorderPolicy, and the KPI dataclasses (FillRateReport,
InventoryHealthReport, OrderBookReport).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Final

import numpy as np

DEFAULT_CARGO_CAPACITY: Final[int] = 20
DEFAULT_DEMAND_RATE: Final[float] = 0.05
DEFAULT_HOLDING_COST_PER_UNIT: Final[float] = 0.001
DEFAULT_STOCKOUT_COST_PER_UNIT: Final[float] = 0.05
DEFAULT_REORDER_FRACTION: Final[float] = 0.3
DEFAULT_ORDER_UP_TO_FRACTION: Final[float] = 0.8
DEFAULT_FULFILLED_HISTORY_CAP: Final[int] = 4096
DEFAULT_CARRIER_REWARDS_CAP: Final[int] = 200


@dataclass(slots=True)
class CargoConstraints:
    """Per-agent cargo capacity. Stored on the Market alongside wallets."""

    capacity: dict[int, int]

    def available(self, agent_id: int, current_inventory: dict[int, int]) -> int:
        """How many more units agent_id can pick up right now."""
        used = sum(current_inventory.values())
        return max(0, self.capacity.get(agent_id, DEFAULT_CARGO_CAPACITY) - used)

    @classmethod
    def uniform(cls, n_agents: int, capacity: int = DEFAULT_CARGO_CAPACITY) -> CargoConstraints:
        """Build a uniform fleet (all agents same capacity)."""
        return cls(capacity=dict.fromkeys(range(n_agents), capacity))


@dataclass(slots=True)
class DemandModel:
    """Per-city per-product demand rate + backlog tracking.

    `rate[(city, product)]` is units consumed per tick by the city's
    end customers. Backlog accumulates when inventory falls short.
    """

    rate: dict[tuple[int, int], float]
    backlog: dict[tuple[int, int], int] = field(default_factory=dict)
    cumulative_served: int = 0
    cumulative_requested: int = 0
    per_product_served: dict[int, int] = field(default_factory=dict)
    per_product_requested: dict[int, int] = field(default_factory=dict)

    def step(self, market: object) -> dict[str, float]:
        """Consume from city inventories; record served/unmet demand.

        Returns a summary dict for the most recent tick. The caller is
        expected to call this once per tick after `Market.tick`.
        """
        served_now = 0
        requested_now = 0
        for (city, product), rate in self.rate.items():
            requested = max(0, round(rate))  # Tier 1 keeps rates as int per tick
            if requested == 0:
                continue
            requested_now += requested
            ms = market.markets.get(city)  # type: ignore[attr-defined]
            available = ms.inventory.get(product, 0) if ms is not None else 0
            served = min(requested, available)
            served_now += served
            unmet = requested - served
            if served > 0 and ms is not None:
                ms.inventory[product] = max(0, available - served)
                # Pay the city for the consumed goods (revenue side).
                ms.treasury += served * ms.ask_price.get(product, 0.0)
            if unmet > 0:
                self.backlog[(city, product)] = self.backlog.get((city, product), 0) + unmet
            self.per_product_served[product] = self.per_product_served.get(product, 0) + served
            self.per_product_requested[product] = (
                self.per_product_requested.get(product, 0) + requested
            )
        self.cumulative_served += served_now
        self.cumulative_requested += requested_now
        ratio = served_now / max(requested_now, 1)
        return {
            "fill_rate_tick": ratio,
            "served_tick": float(served_now),
            "requested_tick": float(requested_now),
        }

    @classmethod
    def uniform(
        cls,
        market: object,
        rate: float = DEFAULT_DEMAND_RATE,
    ) -> DemandModel:
        """Build a demand model with the SAME rate per (city, product) pair."""
        rates: dict[tuple[int, int], float] = {}
        for city_id, ms in market.markets.items():  # type: ignore[attr-defined]
            for product_id in ms.stocked_products:
                rates[(int(city_id), int(product_id))] = float(rate)
        return cls(rate=rates)


@dataclass(slots=True)
class Order:
    """A pending purchase from a city, waiting for a carrier.

    `assigned_to` carries the id of the agent dispatched to fulfil
    this order. `None` means the order is still in the unassigned pool
    and a dispatcher should pick a carrier for it on the next tick.
    """

    id: int
    city: int
    product: int
    quantity: int
    placed_tick: int
    reward: float
    fulfilled_tick: int | None = None
    fulfilled_by: int | None = None
    assigned_to: int | None = None
    assigned_tick: int | None = None


@dataclass(slots=True)
class LogisticsMempool:
    """Pending + fulfilled order book.

    Phase 6a Tier 4: also exposes a bounded ``recent_carrier_rewards``
    deque of ``(agent_id, reward)`` pairs appended on every real (non-
    phantom) fulfilment. ``LogisticsRewardShaper`` reads it to issue
    per-agent dispatch bonuses without re-scanning the full fulfilled
    book on every env step.
    """

    pending: list[Order] = field(default_factory=list)
    fulfilled: deque[Order] = field(
        default_factory=lambda: deque(maxlen=DEFAULT_FULFILLED_HISTORY_CAP)
    )
    next_id: int = 0
    recent_carrier_rewards: deque[tuple[int, float]] = field(
        default_factory=lambda: deque(maxlen=DEFAULT_CARRIER_REWARDS_CAP)
    )
    last_fulfilment_tick: int = -1
    total_carrier_fulfilments: int = 0
    # Monotonic count of real-carrier fulfilments since boot. Survives
    # the recent_carrier_rewards deque's left-trim, so subscribers like
    # ``LogisticsRewardShaper`` can drain only the entries appended
    # since the last time they consumed.

    def place(
        self,
        *,
        city: int,
        product: int,
        quantity: int,
        tick: int,
        reward: float,
        assigned_to: int | None = None,
    ) -> Order:
        order = Order(
            id=self.next_id,
            city=city,
            product=product,
            quantity=quantity,
            placed_tick=tick,
            reward=reward,
            assigned_to=assigned_to,
            assigned_tick=tick if assigned_to is not None else None,
        )
        self.next_id += 1
        self.pending.append(order)
        return order

    def fulfil(self, order_id: int, agent_id: int, tick: int) -> Order | None:
        """Mark an order fulfilled and return it. Idempotent on already-fulfilled.

        Real carriers (``agent_id != -1``) also push an
        ``(agent_id, reward)`` entry into ``recent_carrier_rewards`` so
        downstream consumers (the MAPPO logistics shaper, the
        ``/learning/carrier-reward-stream`` endpoint) can read a fixed-
        size rolling window without scanning the full fulfilled history.
        """
        for i, o in enumerate(self.pending):
            if o.id == order_id:
                o.fulfilled_tick = tick
                o.fulfilled_by = agent_id
                self.pending.pop(i)
                self.fulfilled.append(o)
                if agent_id != -1:
                    self.recent_carrier_rewards.append((int(agent_id), float(o.reward)))
                    self.last_fulfilment_tick = int(tick)
                    self.total_carrier_fulfilments += 1
                return o
        return None

    def lead_time_stats(self) -> dict[str, float]:
        """Median + p95 lead time across fulfilled orders. Empty → all zeros."""
        if not self.fulfilled:
            return {"median": 0.0, "p95": 0.0, "n_fulfilled": 0.0}
        lead_times = sorted(
            (o.fulfilled_tick - o.placed_tick)
            for o in self.fulfilled
            if o.fulfilled_tick is not None
        )
        if not lead_times:
            return {"median": 0.0, "p95": 0.0, "n_fulfilled": 0.0}
        mid = len(lead_times) // 2
        median = float(lead_times[mid])
        p95_idx = max(0, int(len(lead_times) * 0.95) - 1)
        p95 = float(lead_times[min(p95_idx, len(lead_times) - 1)])
        return {"median": median, "p95": p95, "n_fulfilled": float(len(lead_times))}


@dataclass(slots=True)
class ReorderPolicy:
    """(s, S) reorder policy per (city, product).

    When inventory[city][product] + outstanding_orders < s[(city, product)],
    place an order for S - inventory - outstanding.
    """

    s: dict[tuple[int, int], int]
    big_s: dict[tuple[int, int], int]
    base_reward: float = 5.0
    _baseline_s: dict[tuple[int, int], int] = field(default_factory=dict)
    _volatility_until_tick: int = -1
    _volatility_multiplier: float = 1.0

    def react_to_volatility(
        self, sigma_signal: float, current_tick: int, decay_ticks: int = 60
    ) -> None:
        """Bump reorder points to defend against forecasted volatility.

        ``sigma_signal`` is the GARCH sigma^2 spike fraction over baseline
        (e.g. 1.5 = +150%). We multiply ``s`` by ``(1 + min(sigma_signal,
        2.0))`` so volatility triggers earlier reorders (defensive
        stocking). Decays back to baseline after ``decay_ticks``.
        Idempotent: re-calling refreshes the decay window without
        compounding the multiplier.
        """
        if not self._baseline_s:
            self._baseline_s = dict(self.s)
        mult = 1.0 + min(max(sigma_signal, 0.0), 2.0)
        self._volatility_multiplier = mult
        self._volatility_until_tick = current_tick + decay_ticks
        for key, base in self._baseline_s.items():
            self.s[key] = max(1, int(base * mult))

    def tick(self, current_tick: int) -> None:
        """Revert to baseline if the volatility window expired."""
        if (
            self._volatility_multiplier != 1.0
            and current_tick >= self._volatility_until_tick
            and self._baseline_s
        ):
            self.s = dict(self._baseline_s)
            self._volatility_multiplier = 1.0

    @classmethod
    def fractional(
        cls,
        market: object,
        s_fraction: float = DEFAULT_REORDER_FRACTION,
        S_fraction: float = DEFAULT_ORDER_UP_TO_FRACTION,  # noqa: N803 — (s, S) is the OR convention
    ) -> ReorderPolicy:
        """Build (s, S) as fractions of each market's max_inventory."""
        s: dict[tuple[int, int], int] = {}
        big_s: dict[tuple[int, int], int] = {}
        for city_id, ms in market.markets.items():  # type: ignore[attr-defined]
            cap = ms.max_inventory
            for product_id in ms.stocked_products:
                s[(int(city_id), int(product_id))] = max(1, int(cap * s_fraction))
                big_s[(int(city_id), int(product_id))] = max(2, int(cap * S_fraction))
        return cls(s=s, big_s=big_s)

    def evaluate(
        self,
        market: object,
        mempool: LogisticsMempool,
        tick: int,
    ) -> int:
        """Per-tick: place orders for (city, product) below s. Returns count placed."""
        placed = 0
        # Precompute outstanding-by-key for O(1) lookup
        outstanding: dict[tuple[int, int], int] = {}
        for o in mempool.pending:
            outstanding[(o.city, o.product)] = outstanding.get((o.city, o.product), 0) + o.quantity
        for (city, product), s_val in self.s.items():
            ms = market.markets.get(city)  # type: ignore[attr-defined]
            if ms is None:
                continue
            inv = ms.inventory.get(product, 0)
            out_qty = outstanding.get((city, product), 0)
            if inv + out_qty < s_val:
                target = self.big_s.get((city, product), s_val + 1)
                qty = max(0, target - inv - out_qty)
                if qty > 0:
                    urgency = 1.0 - min(1.0, inv / max(s_val, 1))
                    reward = self.base_reward * (1.0 + urgency)
                    mempool.place(
                        city=city, product=product, quantity=qty, tick=tick, reward=reward
                    )
                    placed += 1
        return placed


@dataclass(frozen=True, slots=True)
class FillRateReport:
    """Overall + per-product fill rate snapshot."""

    overall_fill_rate: float
    per_product: tuple[tuple[int, float], ...]  # (product_id, fill_rate)
    total_served: int
    total_requested: int
    total_backlog: int


@dataclass(frozen=True, slots=True)
class InventoryHealthReport:
    """Per-city per-product inventory snapshot + cost summary."""

    cells: tuple[tuple[int, int, int, int], ...]
    # (city, product, current_inventory, max_inventory)
    holding_cost_total: float
    stockout_cost_total: float
    n_stockouts: int


@dataclass(frozen=True, slots=True)
class OrderBookReport:
    """Pending + fulfilled orders + lead-time stats."""

    n_pending: int
    n_fulfilled: int
    median_lead_time_ticks: float
    p95_lead_time_ticks: float
    pending_sample: tuple[tuple[int, int, int, int, int, float], ...]
    # (id, city, product, quantity, placed_tick, reward)


@dataclass(frozen=True, slots=True)
class CargoUtilizationReport:
    """Per-agent cargo capacity + current usage."""

    per_agent: tuple[tuple[int, int, int, float], ...]
    # (agent_id, used, capacity, utilization_ratio)
    mean_utilization: float


@dataclass(frozen=True, slots=True)
class DispatchReport:
    """Carrier-dispatch snapshot: assignments, earnings, efficiency.

    `agent_earnings` is keyed by agent_id (carrier-only); the phantom
    carrier (-1) used by the safety fallback is excluded so it doesn't
    skew the per-carrier average. `mean_carrier_revenue` averages over
    agents that have actually been paid at least once.
    """

    n_pending: int
    n_assigned: int
    n_unassigned: int
    n_fulfilled: int
    n_placed: int
    n_phantom_fulfilled: int
    agent_earnings: tuple[tuple[int, float], ...]  # (agent_id, total_reward)
    mean_carrier_revenue: float
    fulfilment_efficiency: float
    top_carriers: tuple[tuple[int, float], ...]  # top 10 (agent_id, reward)


def compute_fill_rate(demand: DemandModel) -> FillRateReport:
    per_product: list[tuple[int, float]] = []
    for product, requested in demand.per_product_requested.items():
        served = demand.per_product_served.get(product, 0)
        per_product.append((int(product), served / max(requested, 1)))
    per_product.sort()
    total_backlog = sum(demand.backlog.values())
    overall = demand.cumulative_served / max(demand.cumulative_requested, 1)
    return FillRateReport(
        overall_fill_rate=overall,
        per_product=tuple(per_product),
        total_served=demand.cumulative_served,
        total_requested=demand.cumulative_requested,
        total_backlog=int(total_backlog),
    )


def compute_inventory_health(
    market: object,
    holding_cost_per_unit: float = DEFAULT_HOLDING_COST_PER_UNIT,
    stockout_cost_per_unit: float = DEFAULT_STOCKOUT_COST_PER_UNIT,
    demand: DemandModel | None = None,
) -> InventoryHealthReport:
    cells: list[tuple[int, int, int, int]] = []
    holding_total = 0.0
    n_stockouts = 0
    for city_id, ms in market.markets.items():  # type: ignore[attr-defined]
        for product_id in ms.stocked_products:
            inv = ms.inventory.get(product_id, 0)
            cells.append((int(city_id), int(product_id), int(inv), int(ms.max_inventory)))
            holding_total += inv * holding_cost_per_unit
            if inv == 0:
                n_stockouts += 1
    backlog_total = sum(demand.backlog.values()) if demand is not None else 0
    stockout_total = backlog_total * stockout_cost_per_unit
    return InventoryHealthReport(
        cells=tuple(cells),
        holding_cost_total=holding_total,
        stockout_cost_total=stockout_total,
        n_stockouts=n_stockouts,
    )


def compute_order_book(mempool: LogisticsMempool, n_sample: int = 32) -> OrderBookReport:
    stats = mempool.lead_time_stats()
    sample = mempool.pending[:n_sample]
    return OrderBookReport(
        n_pending=len(mempool.pending),
        n_fulfilled=len(mempool.fulfilled),
        median_lead_time_ticks=stats["median"],
        p95_lead_time_ticks=stats["p95"],
        pending_sample=tuple(
            (o.id, o.city, o.product, o.quantity, o.placed_tick, o.reward) for o in sample
        ),
    )


def compute_cargo_utilization(
    cargo: CargoConstraints,
    market: object,
) -> CargoUtilizationReport:
    rows: list[tuple[int, int, int, float]] = []
    utilizations: list[float] = []
    for wallet in market.wallets.values():  # type: ignore[attr-defined]
        used = sum(wallet.inventory.values())
        cap = cargo.capacity.get(wallet.agent_id, DEFAULT_CARGO_CAPACITY)
        ratio = used / max(cap, 1)
        rows.append((int(wallet.agent_id), int(used), int(cap), float(ratio)))
        utilizations.append(ratio)
    mean = float(np.mean(utilizations)) if utilizations else 0.0
    return CargoUtilizationReport(per_agent=tuple(rows), mean_utilization=mean)


def compute_dispatch_report(market: object, mempool: LogisticsMempool) -> DispatchReport:
    """KPIs for the carrier-dispatch layer.

    Aggregates per-agent earnings over the lifetime fulfilled book and
    bins the pending side by assignment state. The phantom carrier id
    (-1) is reported in its own counter but excluded from per-carrier
    averages so the metric reflects REAL agents.
    """
    n_assigned = sum(1 for o in mempool.pending if o.assigned_to is not None)
    n_unassigned = len(mempool.pending) - n_assigned
    earnings: dict[int, float] = {}
    n_phantom = 0
    for o in mempool.fulfilled:
        carrier = o.fulfilled_by
        if carrier is None:
            continue
        if carrier < 0:
            n_phantom += 1
            continue
        earnings[int(carrier)] = earnings.get(int(carrier), 0.0) + float(o.reward)
    # Pre-fill every wallet so the dashboard can render a stable fleet
    # roster even before anyone has earned. Existing entries (carriers
    # that already earned) are preserved.
    wallets = getattr(market, "wallets", {})
    for aid in wallets:
        earnings.setdefault(int(aid), 0.0)
    rows = sorted(earnings.items(), key=lambda kv: (-kv[1], kv[0]))
    paid = [v for _, v in rows if v > 0.0]
    mean_paid = float(np.mean(paid)) if paid else 0.0
    n_placed = mempool.next_id
    efficiency = len(mempool.fulfilled) / max(n_placed, 1)
    top = tuple((int(a), float(r)) for a, r in rows[:10])
    return DispatchReport(
        n_pending=len(mempool.pending),
        n_assigned=n_assigned,
        n_unassigned=n_unassigned,
        n_fulfilled=len(mempool.fulfilled),
        n_placed=n_placed,
        n_phantom_fulfilled=n_phantom,
        agent_earnings=tuple((int(a), float(r)) for a, r in rows),
        mean_carrier_revenue=mean_paid,
        fulfilment_efficiency=efficiency,
        top_carriers=top,
    )


def assign_carriers(
    *,
    mempool: LogisticsMempool,
    market: object,
    arena: object,
    agent_positions: dict[int, int],
    cargo: CargoConstraints,
    tick: int,
    blocked_agents: set[int] | None = None,
) -> int:
    """Greedy nearest-agent dispatcher.

    For every order in `mempool.pending` with `assigned_to is None`,
    pick the closest agent (by shortest-path distance in `arena.graph`,
    falling back to hop count via BFS when edge weights are missing)
    that (a) is not already assigned to a different pending order and
    (b) has spare cargo capacity ≥ order.quantity. Returns the number
    of orders newly assigned this call.

    ``blocked_agents`` (Tier 2): when provided, those agent ids are
    excluded from dispatch consideration — a security block has teeth
    not just on trade settlement but also on logistics participation.
    Default ``None`` preserves backwards compatibility for tests and
    legacy callers that don't track the blocked set.

    Performance: when there are multiple unassigned orders we pre-compute
    a single-source Dijkstra from each unique destination city (orders
    typically share cities), turning the inner agent loop into a dict
    lookup. The previous shape -- `nx.shortest_path_length(graph, pos,
    city)` per (order, agent) pair -- was O(orders * agents * Dijkstra)
    and showed up as the hottest path of the analytics tick in stress
    profiles (2026-05-23).
    """
    unassigned = [o for o in mempool.pending if o.assigned_to is None]
    if not unassigned:
        return 0
    busy: set[int] = {o.assigned_to for o in mempool.pending if o.assigned_to is not None}  # type: ignore[misc]
    blocked: set[int] = set(blocked_agents) if blocked_agents else set()
    import networkx as nx  # local import keeps the module light at import time

    graph = getattr(arena, "graph", None)
    wallets = getattr(market, "wallets", {})
    # Pre-compute single-source shortest-path lengths from each unique
    # destination city. With <= a few dozen cities and an order book that
    # tends to cluster on the same cities, this collapses Orders * Agents
    # Dijkstra calls into Cities single-source passes.
    distances_from: dict[int, dict[int, float]] = {}
    if graph is not None:
        unique_cities: set[int] = {o.city for o in unassigned}
        for city in unique_cities:
            try:
                distances_from[city] = dict(
                    nx.single_source_dijkstra_path_length(graph, city, weight="weight")
                )
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue

    n_assigned = 0
    for order in unassigned:
        best_agent: int | None = None
        best_distance = float("inf")
        city_distances = distances_from.get(order.city)
        for agent_id, pos in agent_positions.items():
            if agent_id in busy:
                continue
            if agent_id in blocked:
                continue
            wallet = wallets.get(agent_id)
            if wallet is None:
                continue
            capacity = cargo.capacity.get(agent_id, DEFAULT_CARGO_CAPACITY)
            used = sum(wallet.inventory.values())
            if capacity - used < order.quantity:
                continue
            if graph is None or pos == order.city:
                distance = 0.0 if pos == order.city else 1.0
            elif city_distances is not None:
                if pos not in city_distances:
                    continue
                distance = float(city_distances[pos])
            else:
                try:
                    distance = float(
                        nx.shortest_path_length(graph, pos, order.city, weight="weight")
                    )
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue
            if distance < best_distance:
                best_distance = distance
                best_agent = agent_id
        if best_agent is not None:
            order.assigned_to = best_agent
            order.assigned_tick = tick
            busy.add(best_agent)
            n_assigned += 1
    return n_assigned
