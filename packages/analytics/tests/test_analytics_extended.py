"""Smoke tests for the second-wave analytics modules."""

from __future__ import annotations

import numpy as np
from penumbra_analytics import (
    bayesian,
    clustering,
    survival,
    time_series,
    topology,
)
from penumbra_analytics import transport as analytics_transport
from penumbra_analytics.dashboard_pipeline import DashboardPipeline

# ── Clustering ────────────────────────────────────────────────────


def test_hdbscan_finds_two_clusters() -> None:
    rng = np.random.default_rng(seed=42)
    cluster_a = rng.normal(loc=(-3, -3), scale=0.3, size=(40, 2))
    cluster_b = rng.normal(loc=(3, 3), scale=0.3, size=(40, 2))
    noise = rng.uniform(low=-1, high=1, size=(5, 2))
    points = np.vstack([cluster_a, cluster_b, noise])
    result = clustering.hdbscan_cluster(points, min_cluster_size=10)
    assert result.n_clusters == 2


# ── Time series ──────────────────────────────────────────────────


def test_arima_one_step_returns_finite_forecast() -> None:
    rng = np.random.default_rng(seed=42)
    n = 80
    series = np.zeros(n)
    for t in range(1, n):
        series[t] = 0.6 * series[t - 1] + rng.standard_normal()
    forecast = time_series.arima_one_step(series, order=(1, 0, 0))
    assert np.isfinite(forecast.next_value)
    assert forecast.forecast_std > 0


def test_kalman_filter_smooths_white_noise() -> None:
    rng = np.random.default_rng(seed=42)
    truth = 5.0
    n = 200
    obs = truth + rng.standard_normal(n) * 0.5
    filtered = time_series.kalman_filter_1d(obs, process_var=0.001, observation_var=0.25)
    # Filtered series should be closer to truth than the raw obs.
    assert np.mean(np.abs(filtered - truth)) < np.mean(np.abs(obs - truth))


def test_changepoint_detection_on_mean_jump() -> None:
    rng = np.random.default_rng(seed=42)
    series = np.concatenate([rng.normal(0, 0.5, 100), rng.normal(3, 0.5, 100)])
    cps = time_series.detect_mean_changepoints(series, penalty=5.0)
    # At least one detected change should be near the true index (100).
    assert any(abs(cp - 100) < 15 for cp in cps)


# ── Bayesian (NumPyro SVI) ───────────────────────────────────────


def test_beta_binomial_posterior_concentrates_correctly() -> None:
    # 70 successes in 100 trials → posterior mean near 0.7.
    posterior = bayesian.beta_binomial_posterior(70, 100, n_iters=600, seed=7)
    assert 0.55 < posterior.mean < 0.85
    assert posterior.std < 0.2


def test_linear_regression_posterior_recovers_slope() -> None:
    rng = np.random.default_rng(seed=11)
    n = 80
    x = rng.standard_normal(n).astype(np.float64)
    y = 0.5 + 2.0 * x + 0.3 * rng.standard_normal(n)
    estimates = bayesian.linear_regression_posterior(x, y, n_iters=800, seed=11)
    assert abs(estimates["alpha"].mean - 0.5) < 0.3
    assert abs(estimates["beta"].mean - 2.0) < 0.3


# ── Survival ─────────────────────────────────────────────────────


def test_kaplan_meier_on_simple_dataset() -> None:
    durations = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    events = np.array([True, False, True, True, False, True, True, True])
    curve = survival.kaplan_meier(durations, events)
    # Survival is monotonically non-increasing.
    assert np.all(np.diff(curve.survival) <= 1e-9)
    # And bounded in [0, 1].
    assert curve.survival.min() >= 0.0
    assert curve.survival.max() <= 1.0


def test_cox_recovers_protective_covariate() -> None:
    """A covariate that delays failure should land HR < 1."""
    rng = np.random.default_rng(seed=42)
    n = 200
    covariate = rng.standard_normal(n)
    # Subjects with HIGH covariate values "live longer".
    baseline = rng.exponential(scale=1.0, size=n)
    durations = baseline * np.exp(0.8 * covariate)
    events = np.ones(n, dtype=bool)
    result = survival.cox_proportional_hazards(
        durations,
        events,
        {"protective": covariate},
    )
    assert result.hazard_ratios["protective"] < 1.0


# ── Topology ─────────────────────────────────────────────────────


def test_persistence_on_circle_yields_h1_feature() -> None:
    """100 points uniformly on a circle should produce a long H1 bar."""
    n = 100
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    circle = np.column_stack([np.cos(angles), np.sin(angles)])
    diagram = topology.persistence_from_points(circle, max_dim=1)
    assert diagram.h1.shape[0] >= 1
    # Total persistence in H1 should be non-trivial.
    assert topology.total_persistence(diagram.h1) > 0.1


# ── Optimal transport ────────────────────────────────────────────


def test_sinkhorn_plan_marginals() -> None:
    source = np.array([0.5, 0.3, 0.2])
    target = np.array([0.1, 0.6, 0.3])
    plan_res = analytics_transport.sinkhorn_plan(source, target, reg=0.5)
    # Plan rows should sum to source, cols to target (within reg tolerance).
    np.testing.assert_allclose(plan_res.plan.sum(axis=1), source, atol=5e-2)
    np.testing.assert_allclose(plan_res.plan.sum(axis=0), target, atol=5e-2)
    assert plan_res.cost > 0


def test_wasserstein_1d_zero_when_equal() -> None:
    h = np.array([1.0, 2.0, 3.0, 4.0])
    assert analytics_transport.wasserstein_1d(h, h) == 0.0


def test_wasserstein_1d_positive_when_shifted() -> None:
    a = np.array([1.0, 0.0, 0.0])
    b = np.array([0.0, 0.0, 1.0])
    assert analytics_transport.wasserstein_1d(a, b) > 0


# ── Dashboard pipeline ───────────────────────────────────────────


def test_pipeline_observe_and_recompute() -> None:
    pipeline = DashboardPipeline(
        cadences={
            "descriptive": 0.0,
            "clustering": 0.0,
            "arima": 9999.0,
            "changepoints": 0.0,
            "sinkhorn": 0.0,
            "topology": 9999.0,
            "bayesian": 9999.0,
            "var95": 0.0,
        }
    )
    rng = np.random.default_rng(seed=42)
    for t in range(60):
        positions = rng.standard_normal(8)
        heatmap = rng.standard_normal(16) ** 2
        pipeline.observe(tick=t, positions=positions, heatmap=heatmap)

    snapshot = pipeline.recompute()
    assert snapshot.tick == 59
    assert snapshot.summary is not None
    assert snapshot.hdbscan_n_clusters is not None
    assert snapshot.var95 is not None
