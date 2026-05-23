"""Phase 6a Tier 3 — DP-budget-aware analytics cadence.

Concept taught: the analytics pipeline reacts to a privacy-budget
shortage by SLOWING DOWN its heaviest consumers (so the remaining
budget lasts longer) and by flipping a degraded-mode flag the
operator can see. These tests pin the contract.
"""

from __future__ import annotations

from penumbra_analytics.dashboard_pipeline import DashboardPipeline


def test_degrade_for_dp_warning_halves_heavy_consumer_cadences() -> None:
    pipeline = DashboardPipeline()
    before = {key: pipeline.cadences[key] for key in ("garch", "bayesian", "topics")}
    pipeline.degrade_for_dp_warning()
    for key, base in before.items():
        assert pipeline.cadences[key] == base * 2.0


def test_degrade_for_dp_warning_is_idempotent() -> None:
    pipeline = DashboardPipeline()
    before = {key: pipeline.cadences[key] for key in ("garch", "bayesian", "topics")}
    pipeline.degrade_for_dp_warning()
    pipeline.degrade_for_dp_warning()
    pipeline.degrade_for_dp_warning()
    for key, base in before.items():
        # Doubled exactly once, not three times.
        assert pipeline.cadences[key] == base * 2.0


def test_degrade_for_dp_warning_leaves_other_cadences_untouched() -> None:
    pipeline = DashboardPipeline()
    untouched_keys = [k for k in pipeline.cadences if k not in {"garch", "bayesian", "topics"}]
    before = {k: pipeline.cadences[k] for k in untouched_keys}
    pipeline.degrade_for_dp_warning()
    for k, base in before.items():
        assert pipeline.cadences[k] == base


def test_enter_dp_fallback_flips_degraded_flag() -> None:
    pipeline = DashboardPipeline()
    assert pipeline._dp_degraded is False
    assert pipeline._dp_degradation_reason is None
    pipeline.enter_dp_fallback()
    assert pipeline._dp_degraded is True
    assert pipeline._dp_degradation_reason == "dp_budget_exhausted"


def test_enter_dp_fallback_is_idempotent() -> None:
    pipeline = DashboardPipeline()
    pipeline.enter_dp_fallback()
    pipeline.enter_dp_fallback()
    pipeline.enter_dp_fallback()
    assert pipeline._dp_degraded is True
    assert pipeline._dp_degradation_reason == "dp_budget_exhausted"
