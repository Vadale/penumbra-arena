"""Phase 6a Tier 1 — CPI-shock emission.

Concept tested: a large, persistent dislocation in the CPI series
triggers a ``cpi.shock`` signal through the pipeline's ``on_signal``
hook. The orchestrator forwards it onto the EventBus where the
crisis-regime handler narrows Market price bands. A quiet CPI series
must NOT emit anything. Mirrors ``garch.spike`` so the two Tier 1
triggers share one observable contract.
"""

from __future__ import annotations

import numpy as np
from penumbra_analytics.dashboard_pipeline import DashboardPipeline


def _build_pipeline_with_fast_inflation() -> tuple[
    DashboardPipeline, list[tuple[str, dict[str, object]]]
]:
    """Pipeline whose inflation cadence is 0 so each recompute() fires it.

    Other cadences are pushed to "never" so the test stays focused on
    the CPI path.
    """
    pipeline = DashboardPipeline(
        cadences={
            "descriptive": 9999.0,
            "clustering": 9999.0,
            "arima": 9999.0,
            "changepoints": 9999.0,
            "sinkhorn": 9999.0,
            "topology": 9999.0,
            "bayesian": 9999.0,
            "var95": 9999.0,
            "topics": 9999.0,
            "regression": 9999.0,
            "cluster_scatter": 9999.0,
            "monte_carlo": 9999.0,
            "pca": 9999.0,
            "arima_forecast": 9999.0,
            "logit": 9999.0,
            "bayesian_posterior": 9999.0,
            "granger": 9999.0,
            "economy": 9999.0,
            "survival": 9999.0,
            "spectral": 9999.0,
            "causal": 9999.0,
            "var_irf": 9999.0,
            "garch": 9999.0,
            "anova": 9999.0,
            "autocorrelation": 9999.0,
            "correlations": 9999.0,
            "permutation": 9999.0,
            "candles": 9999.0,
            "inflation": 0.0,
            "wealth": 9999.0,
        }
    )
    received: list[tuple[str, dict[str, object]]] = []

    def _capture(kind: str, payload: dict[str, object]) -> None:
        received.append((kind, payload))

    pipeline.on_signal = _capture
    return pipeline, received


def _feed_cpi_series(pipeline: DashboardPipeline, series: list[float]) -> None:
    """Push a synthetic CPI series through record_trades(), then recompute."""
    wealth = (1.0, 1.0, 1.0, 1.0, 1.0)
    for tick, value in enumerate(series):
        pipeline.record_trades(
            trades=[],
            money_supply=1000.0,
            price_index=value,
            wealth=wealth,
            tick=tick,
        )
        pipeline.observe(tick=tick, positions=np.zeros(2, dtype=np.float64))
        pipeline.recompute()


def test_cpi_shock_fires_on_large_positive_dislocation() -> None:
    """A 50% jump above the rolling baseline must emit ``cpi.shock``."""
    pipeline, received = _build_pipeline_with_fast_inflation()
    quiet = [100.0] * 10
    spike = [160.0] * 5  # +60% jump — well above the 30% threshold
    _feed_cpi_series(pipeline, quiet + spike)

    kinds = [k for k, _ in received]
    assert "cpi.shock" in kinds
    last = next(p for k, p in received if k == "cpi.shock")
    assert float(last["cpi"]) > float(last["baseline"])  # type: ignore[arg-type]
    assert float(last["ratio"]) > 1.30  # type: ignore[arg-type]


def test_cpi_shock_fires_on_large_negative_dislocation() -> None:
    """A 50% crash below the baseline (deflation) must also emit."""
    pipeline, received = _build_pipeline_with_fast_inflation()
    quiet = [100.0] * 10
    crash = [50.0] * 5  # -50% — well below 1/1.30
    _feed_cpi_series(pipeline, quiet + crash)

    kinds = [k for k, _ in received]
    assert "cpi.shock" in kinds
    last = next(p for k, p in received if k == "cpi.shock")
    assert float(last["ratio"]) < 1.0 / 1.30  # type: ignore[arg-type]


def test_cpi_shock_silent_on_quiet_series() -> None:
    """A flat CPI series must NOT trigger any cpi.shock emit."""
    pipeline, received = _build_pipeline_with_fast_inflation()
    _feed_cpi_series(pipeline, [100.0 + 0.5 * (i % 3) for i in range(30)])

    assert all(k != "cpi.shock" for k, _ in received)


def test_cpi_shock_silent_on_slow_drift() -> None:
    """A gradual 1% drift per tick stays inside the threshold band.

    The EMA baseline tracks slow drifts; only abrupt jumps qualify.
    """
    pipeline, received = _build_pipeline_with_fast_inflation()
    drift = [100.0 * (1.005**i) for i in range(40)]  # ~22% over 40 ticks
    _feed_cpi_series(pipeline, drift)

    assert all(k != "cpi.shock" for k, _ in received)
