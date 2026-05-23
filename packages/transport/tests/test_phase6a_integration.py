"""Phase 6a end-to-end integration story.

Concept tested: one synthetic GARCH spike cascades through the bus
to the reorder policy + the market regime + (transitively) the
dispatched orders. The point is to prove the 5 tiers are not
independent observers — they form a connected system.
"""

from __future__ import annotations

from penumbra_core.arena import ArenaConfig
from penumbra_core.economy import Market
from penumbra_core.logistics import ReorderPolicy
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_transport.events import Event, EventBus


def _build_simple_world():
    seeded = bootstrap(42)
    sim = Simulation.build(
        SimulationConfig(n_agents=5, arena=ArenaConfig(n_nodes=10)),
        seeded,
    )
    market = Market.build(
        nodes=list(sim.arena.graph.nodes()),
        n_agents=5,
        seed=42,
    )
    policy = ReorderPolicy.fractional(market, s_fraction=0.3, S_fraction=0.8)
    return sim, market, policy


def test_garch_spike_cascades_to_reorder_and_market_regime() -> None:
    """Tier 1 cross-pillar story: signal → handlers → state change."""
    _, market, policy = _build_simple_world()
    bus = EventBus()
    baseline_s = dict(policy.s)
    assert market.pricing_regime == "normal"

    def on_garch_spike(event: Event) -> None:
        raw = event.payload.get("ratio", 1.0)
        ratio = float(raw if isinstance(raw, int | float) else 1.0) - 1.0
        policy.react_to_volatility(sigma_signal=ratio, current_tick=event.tick)
        market.set_pricing_regime("volatile", ticks_active=30, current_tick=event.tick)

    bus.subscribe("garch.spike", on_garch_spike)
    bus.emit(Event(kind="garch.spike", tick=10, payload={"ratio": 2.5}))

    for key, base in baseline_s.items():
        assert policy.s[key] == max(1, int(base * 2.5))
    assert market.pricing_regime == "volatile"
    history = bus.recent()
    assert len(history) == 1
    assert history[0].kind == "garch.spike"


def test_market_pricing_regime_decays_back_to_normal() -> None:
    """Tier 1 — decay sanity (also exercised by orchestrator analytics tick)."""
    _, market, _ = _build_simple_world()
    market.set_pricing_regime("crisis", ticks_active=20, current_tick=100)
    market.tick_pricing(115)
    assert market.pricing_regime == "crisis"
    market.tick_pricing(120)
    assert market.pricing_regime == "normal"


def test_reorder_policy_decay_back_to_baseline() -> None:
    """Tier 1 — policy decay sanity."""
    _, _, policy = _build_simple_world()
    baseline = dict(policy.s)
    policy.react_to_volatility(sigma_signal=1.0, current_tick=0, decay_ticks=15)
    assert policy.s != baseline
    policy.tick(15)
    assert policy.s == baseline


def test_event_bus_stats_record_per_kind_metrics() -> None:
    """Tier 1 — observability surface backing the EventGraphChart tile."""
    bus = EventBus()
    bus.subscribe("foo", lambda _e: None)
    bus.subscribe("bar", lambda _e: None)
    for i in range(5):
        bus.emit(Event(kind="foo", tick=i))
    for i in range(3):
        bus.emit(Event(kind="bar", tick=i))
    stats = bus.stats()
    emits: dict[str, int] = stats["emit_counts"]  # type: ignore[assignment]
    assert emits["foo"] == 5
    assert emits["bar"] == 3


def test_cross_tier_handlers_chain_via_recursive_emit() -> None:
    """Verify handlers can queue downstream events safely.

    Simulates: garch.spike → handler emits a downstream `policy.retuned`
    event for another tile to observe. The bus must NOT recurse
    synchronously; the downstream event must fire on the NEXT drain.
    """
    bus = EventBus()
    seen_downstream: list[Event] = []

    def on_garch_spike(event: Event) -> None:
        bus.emit(Event(kind="policy.retuned", tick=event.tick, payload={}))

    bus.subscribe("garch.spike", on_garch_spike)
    bus.subscribe("policy.retuned", seen_downstream.append)
    bus.emit(Event(kind="garch.spike", tick=1))
    assert len(seen_downstream) == 1
    assert seen_downstream[0].kind == "policy.retuned"
