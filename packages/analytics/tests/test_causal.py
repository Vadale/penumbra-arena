"""Tests for the causal-inference module.

Strategy: synthesise data with a *known* true ATE. The standard
Lunceford-Davidian (2004) DGP works well: a binary treatment whose
probability depends on covariates, and an outcome that depends on
both treatment and covariates with a known coefficient.
"""

from __future__ import annotations

import numpy as np
import pytest
from penumbra_analytics import causal


def _synthetic_dataset(
    n: int = 1_000,
    true_ate: float = 2.0,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate (Y, T, X) with a known ATE.

    DGP:
      X ~ N(0, I_3)
      logit(P(T=1 | X)) = 0.5*X_0 - 0.4*X_1 + 0.2*X_2
      Y = true_ate * T + 1.2*X_0 + 0.7*X_1 - 0.3*X_2 + N(0, 0.5)
    """
    rng = np.random.default_rng(seed=seed)
    x = rng.standard_normal((n, 3))
    logit = 0.5 * x[:, 0] - 0.4 * x[:, 1] + 0.2 * x[:, 2]
    p = 1.0 / (1.0 + np.exp(-logit))
    t = (rng.uniform(size=n) < p).astype(int)
    noise = rng.standard_normal(n) * 0.5
    y = true_ate * t + 1.2 * x[:, 0] + 0.7 * x[:, 1] - 0.3 * x[:, 2] + noise
    return y, t, x


def test_estimate_propensity_returns_clipped_probabilities() -> None:
    _, t, x = _synthetic_dataset()
    p = causal.estimate_propensity(t, x, clip=0.1)
    assert p.shape == t.shape
    assert p.min() >= 0.1 - 1e-9
    assert p.max() <= 0.9 + 1e-9


def test_estimate_propensity_validates_shapes() -> None:
    with pytest.raises(ValueError, match="2-D"):
        causal.estimate_propensity(np.array([1, 0]), np.array([1.0, 2.0]))


def test_ipw_recovers_true_ate_within_se() -> None:
    """The IPW estimator should recover the true ATE within ~ 3 SE."""
    y, t, x = _synthetic_dataset(n=2_000, true_ate=2.0, seed=42)
    propensity = causal.estimate_propensity(t, x)
    estimate = causal.ipw_ate(y, t, propensity)
    assert abs(estimate.ate - 2.0) < 3 * estimate.se


def test_aipw_recovers_true_ate_within_se() -> None:
    """AIPW (doubly robust) should also recover the true ATE, often tighter."""
    y, t, x = _synthetic_dataset(n=2_000, true_ate=2.0, seed=42)
    estimate = causal.aipw_ate(y, t, x)
    assert abs(estimate.ate - 2.0) < 3 * estimate.se
    assert estimate.method == "AIPW"


def test_aipw_more_precise_than_naive_difference_in_means() -> None:
    """AIPW should beat the naive mean-of-treated minus mean-of-control,
    which is biased when treatment is confounded with the outcome."""
    y, t, x = _synthetic_dataset(n=2_000, true_ate=2.0, seed=42)
    naive_diff = float(y[t == 1].mean() - y[t == 0].mean())
    aipw = causal.aipw_ate(y, t, x)
    assert abs(aipw.ate - 2.0) < abs(naive_diff - 2.0)
