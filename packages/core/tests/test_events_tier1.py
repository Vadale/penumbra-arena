"""Tier 1 — Stats↔Logistics/Market event-driven reactions."""

from __future__ import annotations

import pytest
from penumbra_core.arena import ArenaConfig
from penumbra_core.economy import Market
from penumbra_core.logistics import ReorderPolicy
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig


def _build_market() -> Market:
    seeded = bootstrap(42)
    sim = Simulation.build(
        SimulationConfig(n_agents=5, arena=ArenaConfig(n_nodes=10)),
        seeded,
    )
    return Market.build(
        nodes=list(sim.arena.graph.nodes()),
        n_agents=5,
        seed=42,
    )


def test_market_set_pricing_regime_persists_until_decay() -> None:
    m = _build_market()
    assert m.pricing_regime == "normal"
    m.set_pricing_regime("volatile", ticks_active=10, current_tick=0)
    assert m.pricing_regime == "volatile"
    m.tick_pricing(5)
    assert m.pricing_regime == "volatile"
    m.tick_pricing(10)
    assert m.pricing_regime == "normal"


def test_market_set_pricing_regime_rejects_unknown() -> None:
    m = _build_market()
    with pytest.raises(ValueError, match="unknown pricing regime"):
        m.set_pricing_regime("apocalypse", ticks_active=10, current_tick=0)


def test_reorder_policy_react_to_volatility_bumps_s() -> None:
    m = _build_market()
    policy = ReorderPolicy.fractional(m, s_fraction=0.3, S_fraction=0.8)
    baseline = dict(policy.s)
    policy.react_to_volatility(sigma_signal=1.0, current_tick=0, decay_ticks=50)
    # All s thresholds doubled (mult = 1 + min(1.0, 2.0) = 2).
    for key, base in baseline.items():
        assert policy.s[key] == max(1, int(base * 2))


def test_reorder_policy_tick_decays_back_to_baseline() -> None:
    m = _build_market()
    policy = ReorderPolicy.fractional(m)
    baseline = dict(policy.s)
    policy.react_to_volatility(sigma_signal=1.0, current_tick=0, decay_ticks=10)
    policy.tick(5)
    assert policy.s != baseline  # still volatile
    policy.tick(10)
    assert policy.s == baseline  # decayed back


def test_reorder_policy_react_idempotent() -> None:
    """Re-calling refreshes the window without compounding."""
    m = _build_market()
    policy = ReorderPolicy.fractional(m)
    policy.react_to_volatility(sigma_signal=0.5, current_tick=0, decay_ticks=10)
    after_first = dict(policy.s)
    policy.react_to_volatility(sigma_signal=0.5, current_tick=5, decay_ticks=10)
    after_second = dict(policy.s)
    assert after_first == after_second  # not compounded


def test_reorder_policy_sigma_signal_clamped_at_2() -> None:
    m = _build_market()
    policy = ReorderPolicy.fractional(m)
    baseline = dict(policy.s)
    # Huge signal — multiplier clamped at 1 + 2 = 3
    policy.react_to_volatility(sigma_signal=99.0, current_tick=0)
    for key, base in baseline.items():
        assert policy.s[key] == max(1, int(base * 3))
