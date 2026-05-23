"""Multi-echelon supply chain (Tier 3 of LOGISTICS_PLAN.md).

Concept taught: how variance amplifies as orders propagate UPSTREAM
through a multi-tier supply chain — the bullwhip effect (Forrester
1961; Lee, Padmanabhan, Whang 1997). Suppliers produce raw goods,
distributors hold intermediate inventory, cities face end-customer
demand. Each tier replenishes from its upstream neighbour with a
deterministic lead time; longer lead times produce LARGER order
variance at upstream tiers even when end-customer demand is
near-constant.

This module is self-contained: it does NOT depend on `economy.Market`
or `logistics.LogisticsMempool`. It builds its own `EchelonNetwork`
out of `SupplyNode`s + lead-time edges. The orchestrator lazily
constructs one from the live arena (20% suppliers / 30% distributors
/ rest cities) and steps it on every analytics tick.

References:
    Forrester, J. W. *Industrial Dynamics* (MIT Press, 1961).
    Lee, Padmanabhan, Whang. "The Bullwhip Effect in Supply Chains."
        *Sloan Management Review* 38(3), 1997.
    Snyder & Shen. *Fundamentals of Supply Chain Theory*, ch. 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

import numpy as np

NodeRole = Literal["supplier", "distributor", "city"]

DEFAULT_LEAD_TIME: Final[int] = 3
DEFAULT_PRODUCTION_RATE: Final[int] = 10
DEFAULT_INITIAL_INVENTORY: Final[int] = 50
DEFAULT_REORDER_POINT: Final[int] = 20
DEFAULT_ORDER_UP_TO: Final[int] = 80
DEFAULT_WINDOW: Final[int] = 200


class EchelonError(Exception):
    """Raised on inconsistent network construction or stepping."""


@dataclass(slots=True)
class SupplyNode:
    """One node of the multi-echelon supply chain.

    `inventory` and `order_history` are keyed by product. Suppliers
    REPLENISH from thin air at `production_rate` per tick; distributors
    + cities replenish via in-flight shipments from upstream.
    """

    id: int
    role: NodeRole
    inventory: dict[int, int] = field(default_factory=dict)
    production_rate: int = DEFAULT_PRODUCTION_RATE
    base_lead_time: int = DEFAULT_LEAD_TIME
    reorder_point: int = DEFAULT_REORDER_POINT
    order_up_to: int = DEFAULT_ORDER_UP_TO
    order_history: dict[int, list[int]] = field(default_factory=dict)


@dataclass(slots=True)
class _Shipment:
    """An in-flight order being delivered after `arrives_at_tick`."""

    product: int
    quantity: int
    destination_id: int
    arrives_at_tick: int


@dataclass(slots=True)
class EchelonNetwork:
    """A directed acyclic supply chain.

    `edges` are (upstream_id, downstream_id, lead_time) triples. The
    network is built from the bottom up: cities sit at tier 0,
    distributors at tier 1, suppliers at tier 2.

    Two derived lookup tables are cached for the per-tick hot path:
      * ``_upstream_index`` — ``downstream_id`` → ``(upstream_id, lead_time)``.
        Built on first ``upstream_of`` call; the topology is immutable
        post-construction so a single dict suffices.
      * ``_role_index`` — role name → tuple of nodes in that role. Built
        lazily on first ``nodes_by_role`` call; same immutability rationale.
    Previously each call did a linear scan of ``edges`` / ``nodes`` which
    was O(N) per tick and showed up in the stress profile (2026-05-23).
    """

    nodes: dict[int, SupplyNode]
    edges: list[tuple[int, int, int]]
    products: tuple[int, ...] = (0,)
    tick: int = 0
    in_flight: list[_Shipment] = field(default_factory=list)
    demand_history: dict[int, list[int]] = field(default_factory=dict)
    _upstream_index: dict[int, tuple[int, int]] | None = field(default=None)
    _role_index: dict[str, tuple[SupplyNode, ...]] | None = field(default=None)

    def upstream_of(self, node_id: int) -> tuple[int, int] | None:
        """Return (upstream_node_id, lead_time) for the first edge above this node."""
        index = self._upstream_index
        if index is None:
            index = {d: (u, lt) for u, d, lt in self.edges}
            self._upstream_index = index
        return index.get(node_id)

    def nodes_by_role(self, role: NodeRole) -> tuple[SupplyNode, ...]:
        index = self._role_index
        if index is None:
            buckets: dict[str, list[SupplyNode]] = {}
            for node in self.nodes.values():
                buckets.setdefault(node.role, []).append(node)
            index = {r: tuple(ns) for r, ns in buckets.items()}
            self._role_index = index
        return index.get(role, ())

    @classmethod
    def build(
        cls,
        *,
        node_ids: list[int],
        supplier_fraction: float = 0.2,
        distributor_fraction: float = 0.3,
        products: tuple[int, ...] = (0,),
        lead_time: int = DEFAULT_LEAD_TIME,
        initial_inventory: int = DEFAULT_INITIAL_INVENTORY,
    ) -> EchelonNetwork:
        """Partition `node_ids` into roles and wire a simple 3-tier topology.

        Cities each fan in to (round-robin) one distributor; distributors
        each fan in to (round-robin) one supplier. The lead time is the
        same on every edge in this baseline; it can be perturbed afterwards
        if a caller wants to study the impact of lead-time heterogeneity.
        """
        if not node_ids:
            raise EchelonError("cannot build network from empty node list")
        if not (0.0 < supplier_fraction < 1.0):
            raise EchelonError("supplier_fraction must be in (0, 1)")
        if not (0.0 < distributor_fraction < 1.0):
            raise EchelonError("distributor_fraction must be in (0, 1)")
        if supplier_fraction + distributor_fraction >= 1.0:
            raise EchelonError("supplier + distributor must leave room for cities")
        n = len(node_ids)
        n_suppliers = max(1, round(n * supplier_fraction))
        n_distributors = max(1, round(n * distributor_fraction))
        n_cities = n - n_suppliers - n_distributors
        if n_cities <= 0:
            raise EchelonError("network has no room for any city nodes")
        sorted_ids = sorted(node_ids)
        supplier_ids = sorted_ids[:n_suppliers]
        distributor_ids = sorted_ids[n_suppliers : n_suppliers + n_distributors]
        city_ids = sorted_ids[n_suppliers + n_distributors :]
        nodes: dict[int, SupplyNode] = {}
        for node_id in supplier_ids:
            nodes[node_id] = SupplyNode(
                id=node_id,
                role="supplier",
                inventory=dict.fromkeys(products, initial_inventory),
                base_lead_time=lead_time,
                order_history={p: [] for p in products},
            )
        for node_id in distributor_ids:
            nodes[node_id] = SupplyNode(
                id=node_id,
                role="distributor",
                inventory=dict.fromkeys(products, initial_inventory),
                base_lead_time=lead_time,
                order_history={p: [] for p in products},
            )
        for node_id in city_ids:
            nodes[node_id] = SupplyNode(
                id=node_id,
                role="city",
                inventory=dict.fromkeys(products, initial_inventory),
                base_lead_time=lead_time,
                order_history={p: [] for p in products},
            )
        edges: list[tuple[int, int, int]] = []
        # City -> Distributor (round-robin).
        for i, city_id in enumerate(city_ids):
            dist_id = distributor_ids[i % len(distributor_ids)]
            edges.append((dist_id, city_id, lead_time))
        # Distributor -> Supplier (round-robin).
        for i, dist_id in enumerate(distributor_ids):
            sup_id = supplier_ids[i % len(supplier_ids)]
            edges.append((sup_id, dist_id, lead_time))
        return cls(
            nodes=nodes,
            edges=edges,
            products=products,
            demand_history={p: [] for p in products},
        )


def step(
    network: EchelonNetwork,
    demand_at_cities: dict[tuple[int, int], int],
) -> dict[str, int]:
    """Advance the network one tick.

    Order of operations per tick:
        1. Suppliers produce `production_rate` per product (raw source).
        2. In-flight shipments whose ETA matches the current tick arrive.
        3. End-customer demand consumes from city inventory (clipped at 0;
           unmet demand is recorded in the city's `order_history` as 0
           because the city's *placed* order is still the (s,S) value).
        4. Each non-supplier node evaluates its (s,S) policy against its
           upstream neighbour and dispatches a shipment with that edge's
           lead time when below the reorder point.

    Returns a summary dict with the totals consumed at this tick.
    """
    tick = network.tick
    # 1. Production at suppliers.
    for sup in network.nodes_by_role("supplier"):
        for product in network.products:
            sup.inventory[product] = sup.inventory.get(product, 0) + sup.production_rate
    # 2. Shipment arrivals.
    arrivals: list[_Shipment] = []
    remaining: list[_Shipment] = []
    for s in network.in_flight:
        (arrivals if s.arrives_at_tick <= tick else remaining).append(s)
    network.in_flight = remaining
    for s in arrivals:
        dest = network.nodes.get(s.destination_id)
        if dest is None:
            continue
        dest.inventory[s.product] = dest.inventory.get(s.product, 0) + s.quantity
    # 3. End-customer demand at cities.
    total_demand = 0
    total_served = 0
    per_product_demand: dict[int, int] = dict.fromkeys(network.products, 0)
    for (city_id, product), requested in demand_at_cities.items():
        city = network.nodes.get(city_id)
        if city is None or city.role != "city":
            continue
        if requested <= 0:
            continue
        available = city.inventory.get(product, 0)
        served = min(available, requested)
        city.inventory[product] = available - served
        total_demand += requested
        total_served += served
        per_product_demand[product] = per_product_demand.get(product, 0) + requested
    for product, total in per_product_demand.items():
        network.demand_history.setdefault(product, []).append(total)
        # Bound the in-memory history so long-running orchestrators don't drift.
        if len(network.demand_history[product]) > DEFAULT_WINDOW * 4:
            network.demand_history[product] = network.demand_history[product][-DEFAULT_WINDOW * 2 :]
    # 4. (s,S) replenishment for every non-supplier.
    n_orders_placed = 0
    outstanding: dict[tuple[int, int], int] = {}
    for s in network.in_flight:
        key = (s.destination_id, s.product)
        outstanding[key] = outstanding.get(key, 0) + s.quantity
    for node in network.nodes.values():
        if node.role == "supplier":
            continue
        upstream = network.upstream_of(node.id)
        if upstream is None:
            continue
        upstream_id, lead_time = upstream
        upstream_node = network.nodes.get(upstream_id)
        if upstream_node is None:
            continue
        for product in network.products:
            inv = node.inventory.get(product, 0)
            on_order = outstanding.get((node.id, product), 0)
            placed_qty = 0
            if inv + on_order < node.reorder_point:
                target = node.order_up_to
                qty = max(0, target - inv - on_order)
                if qty > 0:
                    available_upstream = upstream_node.inventory.get(product, 0)
                    shipped = min(qty, available_upstream)
                    if shipped > 0:
                        upstream_node.inventory[product] = available_upstream - shipped
                        network.in_flight.append(
                            _Shipment(
                                product=product,
                                quantity=shipped,
                                destination_id=node.id,
                                arrives_at_tick=tick + lead_time,
                            )
                        )
                        placed_qty = shipped
                        n_orders_placed += 1
            node.order_history.setdefault(product, []).append(placed_qty)
            if len(node.order_history[product]) > DEFAULT_WINDOW * 4:
                node.order_history[product] = node.order_history[product][-DEFAULT_WINDOW * 2 :]
    network.tick = tick + 1
    return {
        "tick": tick,
        "demand_total": total_demand,
        "served_total": total_served,
        "orders_placed": n_orders_placed,
        "in_flight": len(network.in_flight),
    }


def bullwhip_ratio(
    network: EchelonNetwork,
    window: int = DEFAULT_WINDOW,
) -> dict[str, float]:
    """Return per-tier variance amplification ratio.

    For each tier (city / distributor / supplier-orders), compute the
    variance of the order series over the last `window` ticks, then
    divide by the variance of the end-customer demand series. A ratio
    > 1.0 indicates upstream amplification (bullwhip). Ratios are NaN
    when the demand series has insufficient variance (avoid div-by-zero).
    """
    out: dict[str, float] = {}
    # Demand variance is the denominator: pool across all products.
    demand_series: list[int] = []
    for product, hist in network.demand_history.items():
        del product
        demand_series.extend(hist[-window:])
    base_var = float(np.var(demand_series)) if demand_series else 0.0
    out["demand_variance"] = base_var
    for role in ("city", "distributor", "supplier"):
        nodes = network.nodes_by_role(role)  # type: ignore[arg-type]
        if not nodes:
            out[f"{role}_variance"] = 0.0
            out[f"{role}_bullwhip"] = float("nan") if base_var == 0.0 else 1.0
            continue
        series: list[int] = []
        for node in nodes:
            for product in network.products:
                series.extend(node.order_history.get(product, [])[-window:])
        var = float(np.var(series)) if series else 0.0
        out[f"{role}_variance"] = var
        if base_var <= 0.0:
            out[f"{role}_bullwhip"] = float("nan")
        else:
            out[f"{role}_bullwhip"] = var / base_var
    return out


@dataclass(frozen=True, slots=True)
class EchelonReport:
    """Snapshot of the multi-echelon network for the dashboard."""

    tick: int
    n_suppliers: int
    n_distributors: int
    n_cities: int
    inventory_by_tier: tuple[tuple[str, int], ...]
    # (role, total_inventory_summed_over_nodes_and_products)
    mean_inventory_by_tier: tuple[tuple[str, float], ...]
    in_flight_count: int
    in_flight_quantity: int
    demand_variance: float
    bullwhip_per_tier: tuple[tuple[str, float], ...]
    # (role, variance / demand_variance)
    variance_per_tier: tuple[tuple[str, float], ...]
    edges: tuple[tuple[int, int, int], ...]
    role_for_node: tuple[tuple[int, str], ...]


def compute_echelon_report(
    network: EchelonNetwork,
    window: int = DEFAULT_WINDOW,
) -> EchelonReport:
    """Build a frozen snapshot suitable for the analytics tile."""
    inventory_totals: dict[str, int] = {"supplier": 0, "distributor": 0, "city": 0}
    inventory_counts: dict[str, int] = {"supplier": 0, "distributor": 0, "city": 0}
    for node in network.nodes.values():
        total = sum(node.inventory.values())
        inventory_totals[node.role] += total
        inventory_counts[node.role] += 1
    mean_inv = tuple(
        (role, inventory_totals[role] / inventory_counts[role] if inventory_counts[role] else 0.0)
        for role in ("supplier", "distributor", "city")
    )
    bw = bullwhip_ratio(network, window=window)
    bullwhip_per_tier = tuple(
        (role, float(bw.get(f"{role}_bullwhip", float("nan"))))
        for role in ("supplier", "distributor", "city")
    )
    variance_per_tier = tuple(
        (role, float(bw.get(f"{role}_variance", 0.0)))
        for role in ("supplier", "distributor", "city")
    )
    in_flight_qty = sum(s.quantity for s in network.in_flight)
    return EchelonReport(
        tick=network.tick,
        n_suppliers=len(network.nodes_by_role("supplier")),
        n_distributors=len(network.nodes_by_role("distributor")),
        n_cities=len(network.nodes_by_role("city")),
        inventory_by_tier=tuple(
            (role, inventory_totals[role]) for role in ("supplier", "distributor", "city")
        ),
        mean_inventory_by_tier=mean_inv,
        in_flight_count=len(network.in_flight),
        in_flight_quantity=in_flight_qty,
        demand_variance=float(bw.get("demand_variance", 0.0)),
        bullwhip_per_tier=bullwhip_per_tier,
        variance_per_tier=variance_per_tier,
        edges=tuple(network.edges),
        role_for_node=tuple((nid, n.role) for nid, n in network.nodes.items()),
    )


__all__ = [
    "DEFAULT_INITIAL_INVENTORY",
    "DEFAULT_LEAD_TIME",
    "DEFAULT_ORDER_UP_TO",
    "DEFAULT_PRODUCTION_RATE",
    "DEFAULT_REORDER_POINT",
    "DEFAULT_WINDOW",
    "EchelonError",
    "EchelonNetwork",
    "EchelonReport",
    "NodeRole",
    "SupplyNode",
    "bullwhip_ratio",
    "compute_echelon_report",
    "step",
]
