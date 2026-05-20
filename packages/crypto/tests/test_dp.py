"""Tests for the differential-privacy mechanism + accountant."""

from __future__ import annotations

import numpy as np
import pytest
from penumbra_crypto.dp import (
    BudgetExceededError,
    DPMechanism,
    PrivacyBudget,
    dp_count,
    dp_histogram,
    dp_mean,
)


def _rng() -> np.random.Generator:
    return np.random.default_rng(seed=42)


def test_budget_deducts_correctly() -> None:
    b = PrivacyBudget(epsilon=1.0)
    b.deduct(0.3)
    assert pytest.approx(b.remaining_epsilon, abs=1e-9) == 0.7


def test_budget_rejects_overdraft() -> None:
    b = PrivacyBudget(epsilon=1.0)
    b.deduct(0.6)
    with pytest.raises(BudgetExceededError):
        b.deduct(0.5)


def test_negative_epsilon_rejected() -> None:
    b = PrivacyBudget(epsilon=1.0)
    with pytest.raises(ValueError, match="non-negative"):
        b.deduct(-0.1)


def test_mechanism_requires_positive_epsilon() -> None:
    mech = DPMechanism(PrivacyBudget(epsilon=1.0), rng=_rng())
    with pytest.raises(ValueError, match="epsilon"):
        mech.laplace(10.0, sensitivity=1.0, epsilon=0.0)


def test_mechanism_requires_positive_sensitivity() -> None:
    mech = DPMechanism(PrivacyBudget(epsilon=1.0), rng=_rng())
    with pytest.raises(ValueError, match="sensitivity"):
        mech.laplace(10.0, sensitivity=0.0, epsilon=0.5)


def test_release_deducts_budget_before_noising() -> None:
    """Even if the release happens to land at the true value, the budget moves."""
    mech = DPMechanism(PrivacyBudget(epsilon=1.0), rng=_rng())
    mech.laplace(5.0, sensitivity=1.0, epsilon=0.4)
    assert pytest.approx(mech.budget.remaining_epsilon, abs=1e-9) == 0.6


def test_overdraft_raises_before_drawing_noise() -> None:
    mech = DPMechanism(PrivacyBudget(epsilon=0.2), rng=_rng())
    mech.laplace(1.0, sensitivity=1.0, epsilon=0.15)
    with pytest.raises(BudgetExceededError):
        mech.laplace(1.0, sensitivity=1.0, epsilon=0.1)
    # Budget unchanged after failed release.
    assert pytest.approx(mech.budget.epsilon_spent, abs=1e-9) == 0.15


def test_dp_mean_is_unbiased_in_expectation() -> None:
    """Across many releases, the average noisy mean approaches the true mean."""
    samples = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    true_mean = float(np.mean(samples))
    estimates: list[float] = []
    rng = np.random.default_rng(seed=7)
    for _ in range(1_000):
        # Fresh budget each iteration so we can keep releasing.
        mech = DPMechanism(PrivacyBudget(epsilon=10.0), rng=rng)
        estimates.append(dp_mean(samples, sensitivity=1.0, epsilon=1.0, mechanism=mech))
    # Laplace noise has zero mean → empirical average should be close.
    assert abs(float(np.mean(estimates)) - true_mean) < 0.1


def test_dp_count() -> None:
    mech = DPMechanism(PrivacyBudget(epsilon=1.0), rng=_rng())
    mask = np.array([True, False, True, True, False, True])
    noisy = dp_count(mask, epsilon=0.5, mechanism=mech)
    # Realised count is 4; noisy should be within a few units with high prob.
    assert abs(noisy - 4.0) < 20.0


def test_dp_histogram_preserves_shape() -> None:
    mech = DPMechanism(PrivacyBudget(epsilon=1.0), rng=_rng())
    counts = np.array([10.0, 20.0, 5.0, 0.0, 7.0])
    noisy = dp_histogram(counts, epsilon=0.5, mechanism=mech)
    assert noisy.shape == counts.shape


def test_basic_composition_serial_releases() -> None:
    """Sequential composition: ε's add (Theorem 3.16)."""
    mech = DPMechanism(PrivacyBudget(epsilon=1.0), rng=_rng())
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.3)
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.4)
    assert pytest.approx(mech.budget.epsilon_spent, abs=1e-9) == 0.7
