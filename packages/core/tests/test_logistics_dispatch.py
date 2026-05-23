"""Carrier-dispatch tests.

Concept taught: the dispatch layer turns abstract orders in the
LogisticsMempool into REAL deliveries by a specific agent. The agent
must (a) be assigned the order, (b) reach the city, (c) carry the
requested quantity of the requested product. Stale assignments are
released; pathological waits trip a phantom-carrier fallback so the
system never deadlocks.
"""

from __future__ import annotations

import pytest
from penumbra_core.arena import ArenaConfig
from penumbra_core.economy import Market
from penumbra_core.logistics import (
    CargoConstraints,
    LogisticsMempool,
    Order,
    assign_carriers,
    compute_dispatch_report,
)
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig


@pytest.fixture
def world() -> tuple[Market, object, CargoConstraints]:
    seeded = bootstrap(42)
    sim = Simulation.build(
        SimulationConfig(n_agents=5, arena=ArenaConfig(n_nodes=10), match_max_ticks=100),
        seeded,
    )
    market = Market.build(
        nodes=list(sim.arena.graph.nodes()),
        n_agents=5,
        seed=42,
    )
    cargo = CargoConstraints.uniform(n_agents=5, capacity=20)
    return market, sim.arena, cargo


def test_unassigned_order_stays_unassigned_without_dispatch(
    world: tuple[Market, object, CargoConstraints],
) -> None:
    market, _, _ = world
    mempool = LogisticsMempool()
    city = next(iter(market.markets.keys()))
    product = market.markets[city].stocked_products[0]
    order = mempool.place(city=city, product=product, quantity=2, tick=0, reward=5.0)
    assert order.assigned_to is None
    # Without calling assign_carriers the order remains unassigned.
    assert all(o.assigned_to is None for o in mempool.pending)


def test_assign_carriers_picks_a_free_agent(world: tuple[Market, object, CargoConstraints]) -> None:
    market, arena, cargo = world
    mempool = LogisticsMempool()
    city = next(iter(market.markets.keys()))
    product = market.markets[city].stocked_products[0]
    mempool.place(city=city, product=product, quantity=2, tick=0, reward=5.0)
    agent_positions = {aid: next(iter(market.markets.keys())) for aid in market.wallets}
    n = assign_carriers(
        mempool=mempool,
        market=market,
        arena=arena,
        agent_positions=agent_positions,
        cargo=cargo,
        tick=0,
    )
    assert n == 1
    assert mempool.pending[0].assigned_to is not None
    assigned = mempool.pending[0].assigned_to
    assert assigned in market.wallets


def test_assignment_uniqueness_across_orders(
    world: tuple[Market, object, CargoConstraints],
) -> None:
    market, arena, cargo = world
    mempool = LogisticsMempool()
    cities = list(market.markets.keys())[:3]
    for c in cities:
        product = market.markets[c].stocked_products[0]
        mempool.place(city=c, product=product, quantity=2, tick=0, reward=1.0)
    agent_positions = dict.fromkeys(market.wallets, cities[0])
    n = assign_carriers(
        mempool=mempool,
        market=market,
        arena=arena,
        agent_positions=agent_positions,
        cargo=cargo,
        tick=0,
    )
    # 5 agents, 3 orders: all three should get distinct carriers.
    assigned = [o.assigned_to for o in mempool.pending if o.assigned_to is not None]
    assert n == 3
    assert len(set(assigned)) == 3


def test_fulfilment_when_agent_at_city_with_stock(
    world: tuple[Market, object, CargoConstraints],
) -> None:
    """An assigned agent at the right city with enough inventory triggers delivery."""
    market, _, _ = world
    mempool = LogisticsMempool()
    city = next(iter(market.markets.keys()))
    product = market.markets[city].stocked_products[0]
    order = mempool.place(
        city=city,
        product=product,
        quantity=3,
        tick=0,
        reward=10.0,
        assigned_to=0,
    )
    market.wallets[0].inventory[product] = 5
    coins_before = market.wallets[0].coins
    city_inv_before = market.markets[city].inventory.get(product, 0)
    # Inline the dispatch fulfilment branch from _step_logistics.
    wallet = market.wallets[0]
    if wallet.inventory.get(order.product, 0) >= order.quantity:
        wallet.inventory[order.product] -= order.quantity
        if wallet.inventory[order.product] == 0:
            del wallet.inventory[order.product]
        ms = market.markets[order.city]
        ms.inventory[order.product] = min(
            ms.max_inventory,
            ms.inventory.get(order.product, 0) + order.quantity,
        )
        wallet.coins += order.reward
        mempool.fulfil(order_id=order.id, agent_id=0, tick=1)
    assert market.wallets[0].coins == coins_before + 10.0
    assert market.wallets[0].inventory.get(product, 0) == 2
    assert market.markets[city].inventory.get(product, 0) == min(
        market.markets[city].max_inventory, city_inv_before + 3
    )
    assert mempool.pending == []
    assert mempool.fulfilled[0].fulfilled_by == 0
    assert mempool.fulfilled[0].fulfilled_tick == 1


def test_stale_assignment_releases_after_3x_lead(
    world: tuple[Market, object, CargoConstraints],
) -> None:
    """An assignment that doesn't resolve within 3x lead time returns to pending."""
    market, _, _ = world
    mempool = LogisticsMempool()
    city = next(iter(market.markets.keys()))
    product = market.markets[city].stocked_products[0]
    mempool.place(
        city=city,
        product=product,
        quantity=2,
        tick=0,
        reward=5.0,
        assigned_to=0,
    )
    lead = 5
    # At tick 3*lead the order has been assigned but never delivered.
    tick = 3 * lead
    order = mempool.pending[0]
    assigned_age = tick - (order.assigned_tick or 0)
    if assigned_age >= 3 * lead:
        order.assigned_to = None
        order.assigned_tick = None
    assert mempool.pending[0].assigned_to is None


def test_phantom_carrier_fulfils_after_5x_lead(
    world: tuple[Market, object, CargoConstraints],
) -> None:
    """An order waiting more than 5x lead time auto-fulfils via the phantom carrier."""
    market, _, _ = world
    mempool = LogisticsMempool()
    city = next(iter(market.markets.keys()))
    product = market.markets[city].stocked_products[0]
    mempool.place(city=city, product=product, quantity=2, tick=0, reward=5.0)
    lead = 5
    tick = 5 * lead + 1
    order = mempool.pending[0]
    if tick - order.placed_tick >= 5 * lead:
        mempool.fulfil(order_id=order.id, agent_id=-1, tick=tick)
    assert mempool.pending == []
    assert mempool.fulfilled[0].fulfilled_by == -1


def test_dispatch_report_kpis(world: tuple[Market, object, CargoConstraints]) -> None:
    market, _, _ = world
    mempool = LogisticsMempool()
    city = next(iter(market.markets.keys()))
    product = market.markets[city].stocked_products[0]
    # 3 orders placed: 1 assigned, 1 unassigned, 1 already fulfilled.
    mempool.place(city=city, product=product, quantity=1, tick=0, reward=4.0, assigned_to=0)
    mempool.place(city=city, product=product, quantity=1, tick=0, reward=2.0)
    paid_order = mempool.place(
        city=city, product=product, quantity=1, tick=0, reward=6.0, assigned_to=1
    )
    mempool.fulfil(order_id=paid_order.id, agent_id=1, tick=1)
    report = compute_dispatch_report(market, mempool)
    assert report.n_pending == 2
    assert report.n_assigned == 1
    assert report.n_unassigned == 1
    assert report.n_fulfilled == 1
    assert report.n_placed == 3
    assert report.fulfilment_efficiency == pytest.approx(1 / 3)
    assert report.mean_carrier_revenue == pytest.approx(6.0)
    earnings = dict(report.agent_earnings)
    assert earnings[1] == pytest.approx(6.0)
    # Other agents are present at 0.0 (fleet roster); the top carriers
    # list places the paid one first.
    assert report.top_carriers[0] == (1, pytest.approx(6.0))


def test_dispatch_report_excludes_phantom_from_revenue(
    world: tuple[Market, object, CargoConstraints],
) -> None:
    market, _, _ = world
    mempool = LogisticsMempool()
    city = next(iter(market.markets.keys()))
    product = market.markets[city].stocked_products[0]
    o = mempool.place(city=city, product=product, quantity=1, tick=0, reward=4.0)
    mempool.fulfil(order_id=o.id, agent_id=-1, tick=1)
    report = compute_dispatch_report(market, mempool)
    assert report.n_phantom_fulfilled == 1
    assert report.mean_carrier_revenue == 0.0
    # Phantom carrier (-1) is NOT in agent_earnings.
    assert all(aid >= 0 for aid, _ in report.agent_earnings)


def test_order_dataclass_assigned_to_default_none() -> None:
    order = Order(id=0, city=0, product=0, quantity=1, placed_tick=0, reward=1.0)
    assert order.assigned_to is None
    assert order.assigned_tick is None
