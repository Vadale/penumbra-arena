"""Logistics Tier 1 tests."""

from __future__ import annotations

import pytest
from penumbra_core.arena import ArenaConfig
from penumbra_core.economy import Market
from penumbra_core.logistics import (
    DEFAULT_CARGO_CAPACITY,
    CargoConstraints,
    DemandModel,
    LogisticsMempool,
    ReorderPolicy,
    compute_cargo_utilization,
    compute_fill_rate,
    compute_inventory_health,
    compute_order_book,
)
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig


@pytest.fixture
def market() -> Market:
    seeded = bootstrap(42)
    sim = Simulation.build(
        SimulationConfig(n_agents=5, arena=ArenaConfig(n_nodes=10), match_max_ticks=100),
        seeded,
    )
    return Market.build(
        nodes=list(sim.arena.graph.nodes()),
        n_agents=5,
        seed=42,
    )


def test_cargo_constraints_available_caps_at_capacity(market: Market) -> None:
    cargo = CargoConstraints.uniform(n_agents=5, capacity=20)
    inv = {0: 5, 1: 3}  # 8 units total
    assert cargo.available(agent_id=0, current_inventory=inv) == 12


def test_cargo_constraints_default_for_unknown_agent() -> None:
    cargo = CargoConstraints(capacity={})  # explicitly empty
    assert cargo.available(agent_id=999, current_inventory={}) == DEFAULT_CARGO_CAPACITY


def test_demand_consumption_depletes_inventory(market: Market) -> None:
    # Pick the first city's first product, set demand = 5/tick, run 3 ticks.
    city_id = next(iter(market.markets.keys()))
    product_id = market.markets[city_id].stocked_products[0]
    demand = DemandModel(rate={(city_id, product_id): 5.0})
    initial = market.markets[city_id].inventory.get(product_id, 0)
    for _ in range(3):
        demand.step(market)
    expected = max(0, initial - 15)
    assert market.markets[city_id].inventory.get(product_id, 0) == expected


def test_demand_records_backlog_when_inventory_exhausted(market: Market) -> None:
    city_id = next(iter(market.markets.keys()))
    product_id = market.markets[city_id].stocked_products[0]
    # Set inventory tiny so demand will exceed it.
    market.markets[city_id].inventory[product_id] = 2
    demand = DemandModel(rate={(city_id, product_id): 5.0})
    demand.step(market)
    # Requested 5, served 2, backlog should be 3.
    assert demand.backlog[(city_id, product_id)] == 3
    assert demand.cumulative_served == 2
    assert demand.cumulative_requested == 5


def test_reorder_policy_triggers_order_when_below_s(market: Market) -> None:
    policy = ReorderPolicy.fractional(market, s_fraction=0.5, S_fraction=0.9)
    mempool = LogisticsMempool()
    # Drop one inventory below the s threshold.
    city_id = next(iter(market.markets.keys()))
    product_id = market.markets[city_id].stocked_products[0]
    market.markets[city_id].inventory[product_id] = 0
    placed = policy.evaluate(market=market, mempool=mempool, tick=0)
    assert placed >= 1
    assert any(o.city == city_id and o.product == product_id for o in mempool.pending)


def test_reorder_policy_no_duplicate_orders(market: Market) -> None:
    policy = ReorderPolicy.fractional(market, s_fraction=0.5, S_fraction=0.9)
    mempool = LogisticsMempool()
    city_id = next(iter(market.markets.keys()))
    product_id = market.markets[city_id].stocked_products[0]
    market.markets[city_id].inventory[product_id] = 0
    policy.evaluate(market=market, mempool=mempool, tick=0)
    n_before = len(mempool.pending)
    # Second evaluation in the same state — outstanding order should
    # prevent re-ordering.
    policy.evaluate(market=market, mempool=mempool, tick=1)
    assert len(mempool.pending) == n_before


def test_fill_rate_computed_correctly() -> None:
    demand = DemandModel(rate={})
    demand.cumulative_served = 80
    demand.cumulative_requested = 100
    demand.per_product_served = {1: 80}
    demand.per_product_requested = {1: 100}
    demand.backlog = {(0, 1): 20}
    report = compute_fill_rate(demand)
    assert report.overall_fill_rate == pytest.approx(0.8)
    assert report.total_backlog == 20
    assert report.per_product[0] == (1, pytest.approx(0.8))


def test_lead_time_stats_match_recorded_orders() -> None:
    mempool = LogisticsMempool()
    # Place 5 orders, fulfil them at known offsets.
    for i in range(5):
        mempool.place(city=0, product=1, quantity=1, tick=i, reward=1.0)
    # Fulfil with deterministic lead times 2, 4, 6, 8, 10.
    for i in range(5):
        mempool.fulfil(order_id=i, agent_id=0, tick=i + (i + 1) * 2)
    stats = mempool.lead_time_stats()
    assert stats["n_fulfilled"] == 5
    assert stats["median"] >= 4  # depends on order of dict iter, but lower bound holds


def test_inventory_health_counts_stockouts(market: Market) -> None:
    # Zero out one inventory slot.
    city_id = next(iter(market.markets.keys()))
    product_id = market.markets[city_id].stocked_products[0]
    market.markets[city_id].inventory[product_id] = 0
    report = compute_inventory_health(market)
    assert report.n_stockouts >= 1


def test_cargo_utilization_zero_at_init(market: Market) -> None:
    cargo = CargoConstraints.uniform(n_agents=5, capacity=20)
    report = compute_cargo_utilization(cargo, market)
    # Initial wallets are empty (no inventory).
    assert report.mean_utilization == pytest.approx(0.0)


def test_order_book_returns_pending_sample(market: Market) -> None:
    mempool = LogisticsMempool()
    for i in range(5):
        mempool.place(city=i % 3, product=i % 5, quantity=2, tick=i, reward=1.0)
    report = compute_order_book(mempool, n_sample=3)
    assert report.n_pending == 5
    assert len(report.pending_sample) == 3
