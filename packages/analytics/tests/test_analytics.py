"""Smoke tests for the analytics modules.

These are not exhaustive — the dedicated learning sessions will go deep
on each module. Here we verify the public surface works end-to-end and
the obvious failure modes raise cleanly.
"""

from __future__ import annotations

import networkx as nx
import numpy as np
import polars as pl
import pytest
from penumbra_analytics import descriptive, econometrics, inferential, linalg, monte_carlo

# ── Descriptive ───────────────────────────────────────────────────


def test_summarise_basic_shape() -> None:
    rng = np.random.default_rng(seed=42)
    values = rng.standard_normal(500)
    summary = descriptive.summarise(values)
    assert summary.n == 500
    assert abs(summary.mean) < 0.2  # standard normal, large n
    assert summary.ci95_low < summary.mean < summary.ci95_high


def test_summarise_rejects_2d() -> None:
    with pytest.raises(ValueError, match="1-D"):
        descriptive.summarise(np.zeros((4, 4)))


def test_summarise_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        descriptive.summarise(np.array([], dtype=np.float64))


def test_by_group_polars_lazy() -> None:
    frame = pl.DataFrame(
        {
            "group": ["a", "a", "b", "b", "c"],
            "value": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )
    summary = descriptive.by_group(frame, value_col="value", group_col="group")
    assert summary.shape == (3, 9)
    assert sorted(summary["group"].to_list()) == ["a", "b", "c"]


# ── Inferential ───────────────────────────────────────────────────


def test_mann_whitney_detects_shift() -> None:
    rng = np.random.default_rng(seed=42)
    a = rng.standard_normal(60)
    b = rng.standard_normal(60) + 1.0  # shifted up
    result = inferential.mann_whitney(a, b)
    assert result.reject_at_05


def test_mann_whitney_does_not_reject_identical_dists() -> None:
    rng = np.random.default_rng(seed=42)
    a = rng.standard_normal(60)
    b = rng.standard_normal(60)
    result = inferential.mann_whitney(a, b)
    assert not result.reject_at_05


def test_permutation_detects_shift() -> None:
    rng = np.random.default_rng(seed=7)
    a = rng.normal(0, 1, size=30)
    b = rng.normal(0.8, 1, size=30)
    result = inferential.permutation(a, b, n_perm=999, seed=7)
    assert result.reject_at_05


def test_chi_squared_uniform_distribution() -> None:
    observed = np.array([22, 18, 19, 21])
    expected = np.array([20.0, 20.0, 20.0, 20.0])
    result = inferential.chi_squared_goodness_of_fit(observed.astype(np.float64), expected)
    assert not result.reject_at_05  # uniform-ish; should not reject


def test_cliff_delta_extremes() -> None:
    a = np.array([10.0, 11.0, 12.0])
    b = np.array([1.0, 2.0, 3.0])
    assert inferential.cliff_delta(a, b) == 1.0
    assert inferential.cliff_delta(b, a) == -1.0


# ── Econometrics ──────────────────────────────────────────────────


def test_ols_with_hac_recovers_known_coefficients() -> None:
    rng = np.random.default_rng(seed=42)
    n = 200
    x = rng.standard_normal((n, 2))
    true_beta = np.array([1.5, -0.5])
    y = 0.3 + x @ true_beta + rng.standard_normal(n) * 0.5
    result = econometrics.ols_with_hac(y, x)
    # coefficients[0] is the intercept; next two are slopes.
    assert abs(result.coefficients[0] - 0.3) < 0.15
    assert abs(result.coefficients[1] - 1.5) < 0.1
    assert abs(result.coefficients[2] - (-0.5)) < 0.1
    assert result.r_squared > 0.8


def test_fit_var_orders_correctly() -> None:
    rng = np.random.default_rng(seed=7)
    n = 200
    series = rng.standard_normal((n, 2))
    # Induce dependence on lag 1.
    for t in range(1, n):
        series[t, 0] += 0.5 * series[t - 1, 1]
    result = econometrics.fit_var(series, max_lags=4)
    assert 1 <= result.lag_order <= 4
    assert result.n_series == 2


def test_granger_detects_known_causality() -> None:
    rng = np.random.default_rng(seed=11)
    n = 300
    cause = rng.standard_normal(n)
    effect = np.zeros(n)
    for t in range(2, n):
        effect[t] = 0.6 * cause[t - 1] + 0.2 * effect[t - 1] + rng.standard_normal() * 0.5
    p_values = econometrics.granger_p_value(cause, effect, max_lag=3)
    # At least one lag should reject independence.
    assert any(p < 0.05 for p in p_values.values())


# ── Monte Carlo ───────────────────────────────────────────────────


def test_sobol_sample_shape() -> None:
    pts = monte_carlo.sobol_sample(3, 256)
    assert pts.shape == (256, 3)
    assert pts.min() >= 0.0
    assert pts.max() <= 1.0


def test_integrate_constant_one() -> None:
    """∫ 1 dx over [0,1]^d should be exactly 1."""

    def constant(_: np.ndarray) -> np.ndarray:
        return np.ones(_.shape[0])

    estimate, _ = monte_carlo.integrate(constant, dimensions=2, n_points=256)
    assert abs(estimate - 1.0) < 1e-9


def test_integrate_sum_of_coords() -> None:
    """∫ (x + y) over [0,1]^2 = 1."""

    def linear(pts: np.ndarray) -> np.ndarray:
        return pts.sum(axis=1)

    estimate, _ = monte_carlo.integrate(linear, dimensions=2, n_points=1024)
    assert abs(estimate - 1.0) < 0.02


def test_var_cvar_known_distribution() -> None:
    rng = np.random.default_rng(seed=42)
    losses = rng.exponential(scale=1.0, size=10_000)
    metrics = monte_carlo.var_cvar(losses, confidence=0.95)
    # Exponential(1) has theoretical 95% VaR = -ln(0.05) ≈ 2.996.
    assert abs(metrics.var - 2.996) < 0.2
    assert metrics.cvar > metrics.var


def test_bootstrap_mean_is_centred_on_truth() -> None:
    rng = np.random.default_rng(seed=42)
    sample = rng.standard_normal(500)
    low, high = monte_carlo.bootstrap_mean(sample, n_resamples=999)
    assert low < 0 < high


# ── Linear algebra ────────────────────────────────────────────────


def test_algebraic_connectivity_is_positive_on_connected_graph() -> None:
    graph: nx.Graph = nx.connected_watts_strogatz_graph(20, 4, 0.1, seed=42)  # type: ignore[arg-type]
    assert linalg.algebraic_connectivity(graph) > 0.0


def test_algebraic_connectivity_is_zero_on_disconnected_graph() -> None:
    # Two separated triangles.
    graph: nx.Graph = nx.Graph()
    graph.add_edges_from([(0, 1), (1, 2), (2, 0)])
    graph.add_edges_from([(3, 4), (4, 5), (5, 3)])
    # Normalised Laplacian's smallest non-trivial eigenvalue is 0 for
    # disconnected graphs (multiplicity = number of components).
    assert linalg.algebraic_connectivity(graph) < 1e-6


def test_spectral_clusters_recover_partition() -> None:
    """Two cliques joined by a single edge → 2 clusters."""
    g: nx.Graph = nx.Graph()
    g.add_edges_from([(i, j) for i in range(5) for j in range(5) if i != j])
    g.add_edges_from([(i, j) for i in range(5, 10) for j in range(5, 10) if i != j])
    g.add_edge(0, 5)  # bridge
    labels = linalg.spectral_clusters(g, n_clusters=2)
    # All of {0..4} should share one label; all of {5..9} the other.
    left = set(labels[:5])
    right = set(labels[5:])
    assert len(left) == 1
    assert len(right) == 1
    assert left != right
