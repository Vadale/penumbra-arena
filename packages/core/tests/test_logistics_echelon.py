"""Logistics Tier 3 — multi-echelon supply chain tests."""

from __future__ import annotations

import pytest
from penumbra_core.logistics_echelon import (
    DEFAULT_INITIAL_INVENTORY,
    EchelonError,
    EchelonNetwork,
    bullwhip_ratio,
    compute_echelon_report,
    step,
)


def _build_small_network(lead_time: int = 3) -> EchelonNetwork:
    return EchelonNetwork.build(
        node_ids=list(range(10)),
        supplier_fraction=0.2,
        distributor_fraction=0.3,
        products=(0,),
        lead_time=lead_time,
        initial_inventory=DEFAULT_INITIAL_INVENTORY,
    )


def test_build_partitions_roles_correctly() -> None:
    net = _build_small_network()
    n_supplier = len(net.nodes_by_role("supplier"))
    n_distributor = len(net.nodes_by_role("distributor"))
    n_city = len(net.nodes_by_role("city"))
    assert n_supplier >= 1
    assert n_distributor >= 1
    assert n_city >= 1
    assert n_supplier + n_distributor + n_city == 10


def test_build_creates_full_supply_chain_topology() -> None:
    net = _build_small_network()
    # Every city must have a distributor parent, every distributor a supplier.
    for node in net.nodes.values():
        if node.role == "city":
            up = net.upstream_of(node.id)
            assert up is not None
            assert net.nodes[up[0]].role == "distributor"
        elif node.role == "distributor":
            up = net.upstream_of(node.id)
            assert up is not None
            assert net.nodes[up[0]].role == "supplier"


def test_build_rejects_empty_node_list() -> None:
    with pytest.raises(EchelonError):
        EchelonNetwork.build(node_ids=[])


def test_build_rejects_fractions_that_leave_no_cities() -> None:
    with pytest.raises(EchelonError):
        EchelonNetwork.build(
            node_ids=list(range(10)), supplier_fraction=0.5, distributor_fraction=0.5
        )


def test_step_under_uniform_demand_drains_then_refills_cities() -> None:
    net = _build_small_network(lead_time=2)
    cities = net.nodes_by_role("city")
    initial_total = sum(c.inventory[0] for c in cities)
    demand = {(c.id, 0): 10 for c in cities}  # heavy demand
    # Drain for a few ticks.
    for _ in range(6):
        step(net, demand)
    drained_total = sum(c.inventory[0] for c in cities)
    assert drained_total < initial_total, "cities did not deplete under heavy demand"
    # Now remove demand and let shipments refill from upstream tiers.
    for _ in range(20):
        step(net, {})
    refilled_total = sum(c.inventory[0] for c in cities)
    assert refilled_total > drained_total, "cities did not refill after demand stopped"


def test_step_propagates_orders_upstream() -> None:
    net = _build_small_network(lead_time=2)
    # Drive demand for several ticks so cities order from distributors.
    cities = net.nodes_by_role("city")
    demand = {(c.id, 0): 8 for c in cities}
    for _ in range(10):
        step(net, demand)
    # Both city tier and distributor tier should have placed at least one
    # non-zero order during the run.
    city_orders = sum(sum(c.order_history.get(0, [])) for c in net.nodes_by_role("city"))
    distributor_orders = sum(
        sum(d.order_history.get(0, [])) for d in net.nodes_by_role("distributor")
    )
    assert city_orders > 0
    assert distributor_orders > 0


def test_bullwhip_ratio_increases_with_lead_time() -> None:
    """Classic Forrester result: longer lead time → larger upstream variance."""

    def measure(lead_time: int) -> float:
        net = EchelonNetwork.build(
            node_ids=list(range(20)),
            supplier_fraction=0.2,
            distributor_fraction=0.3,
            products=(0,),
            lead_time=lead_time,
            initial_inventory=DEFAULT_INITIAL_INVENTORY,
        )
        cities = net.nodes_by_role("city")
        # Noisy but mean-stationary demand around 5/tick to inject variance.
        pattern = [4, 6, 5, 7, 3, 6, 4, 5, 7, 4]
        for t in range(80):
            level = pattern[t % len(pattern)]
            demand = {(c.id, 0): level for c in cities}
            step(net, demand)
        bw = bullwhip_ratio(net, window=200)
        return float(bw["distributor_bullwhip"])

    short = measure(1)
    long = measure(8)
    # Either both are NaN (degenerate run with no variance) or long >= short.
    assert (long != long and short != short) or long >= short, (
        f"expected longer lead time to amplify variance, got short={short} long={long}"
    )


def test_compute_echelon_report_returns_all_kpis() -> None:
    net = _build_small_network()
    cities = net.nodes_by_role("city")
    for _ in range(5):
        step(net, {(c.id, 0): 4 for c in cities})
    report = compute_echelon_report(net)
    assert report.n_suppliers >= 1
    assert report.n_distributors >= 1
    assert report.n_cities >= 1
    assert len(report.inventory_by_tier) == 3
    assert len(report.mean_inventory_by_tier) == 3
    assert len(report.bullwhip_per_tier) == 3
    assert len(report.variance_per_tier) == 3
    assert report.demand_variance >= 0.0
    assert len(report.edges) == len(net.edges)
    assert len(report.role_for_node) == len(net.nodes)
    # Every node id appears with a valid role label.
    for nid, role in report.role_for_node:
        assert nid in net.nodes
        assert role in ("supplier", "distributor", "city")


def test_bullwhip_returns_nan_when_no_demand_recorded() -> None:
    net = _build_small_network()
    bw = bullwhip_ratio(net)
    # No demand at all → ratios are nan.
    assert bw["demand_variance"] == 0.0
    assert bw["city_bullwhip"] != bw["city_bullwhip"]  # nan check
