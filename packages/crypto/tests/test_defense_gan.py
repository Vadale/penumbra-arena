"""Tests for the synthetic-trace stub (gan_defenses)."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from penumbra_crypto.defenses.gan_defenses import (
    GANDefenseError,
    demo,
    evaluate_tradeoff,
    fit_gaussian_model,
    synthesise_trajectories,
)


def _real(n: int = 200, d: int = 3) -> np.ndarray:
    """Build a (n, d) matrix with non-trivial pairwise correlations."""
    rng = np.random.default_rng(seed=7)
    base = rng.standard_normal(size=(n, d))
    # A d x d mixing matrix that induces correlations across columns.
    mixer = np.eye(d) + 0.4 * np.tri(d, k=-1) + 0.4 * np.tri(d, k=-1).T
    return base @ mixer.T


def test_fit_gaussian_returns_correct_shapes() -> None:
    real = _real(100, 4)
    mu, cov = fit_gaussian_model(real)
    assert mu.shape == (4,)
    assert cov.shape == (4, 4)


def test_fit_rejects_one_d_input() -> None:
    with pytest.raises(GANDefenseError):
        fit_gaussian_model(np.array([1.0, 2.0, 3.0]))


def test_fit_rejects_singleton_input() -> None:
    with pytest.raises(GANDefenseError):
        fit_gaussian_model(np.array([[1.0, 2.0]]))


def test_fit_rejects_non_finite_input() -> None:
    bad = np.array([[1.0, np.nan], [2.0, 3.0]])
    with pytest.raises(GANDefenseError):
        fit_gaussian_model(bad)


def test_synth_shape() -> None:
    real = _real(100, 3)
    out = synthesise_trajectories(real, n_samples=512, rng=np.random.default_rng(seed=1))
    assert out.shape == (512, 3)


def test_synth_n_samples_must_be_positive() -> None:
    with pytest.raises(GANDefenseError):
        synthesise_trajectories(_real(20, 2), n_samples=0)


def test_synth_correlation_preserve_out_of_range_rejected() -> None:
    with pytest.raises(GANDefenseError):
        synthesise_trajectories(_real(20, 2), n_samples=10, correlation_preserve=1.5)


def test_synth_mean_close_to_real_mean() -> None:
    real = _real(500, 4)
    out = synthesise_trajectories(real, n_samples=10_000, rng=np.random.default_rng(seed=2))
    diff = np.linalg.norm(out.mean(axis=0) - real.mean(axis=0))
    assert diff < 0.2  # 10k samples → CLT bound on the mean estimator


def test_synth_preserves_correlation_at_cp_one() -> None:
    real = _real(500, 3)
    out = synthesise_trajectories(
        real,
        n_samples=10_000,
        correlation_preserve=1.0,
        rng=np.random.default_rng(seed=3),
    )
    real_corr = np.corrcoef(real, rowvar=False)
    synth_corr = np.corrcoef(out, rowvar=False)
    assert np.linalg.norm(real_corr - synth_corr) < 0.2


def test_synth_destroys_correlation_at_cp_zero() -> None:
    """At cp=0 the off-diagonal of the sampled correlation matrix is near 0."""
    real = _real(500, 3)
    out = synthesise_trajectories(
        real,
        n_samples=10_000,
        correlation_preserve=0.0,
        rng=np.random.default_rng(seed=4),
    )
    synth_corr = np.corrcoef(out, rowvar=False)
    off_diag = synth_corr - np.diag(np.diag(synth_corr))
    assert float(np.max(np.abs(off_diag))) < 0.15


def test_evaluate_tradeoff_reports_zero_membership_advantage() -> None:
    real = _real(200, 3)
    report = evaluate_tradeoff(real, n_samples=500, rng=np.random.default_rng(seed=5))
    assert report.privacy_membership_advantage == 0.0
    assert report.n_synth == 500
    assert report.n_features == 3


def test_demo_returns_curve() -> None:
    payload = demo()
    assert payload["available"] is True
    curve = payload["curve"]
    assert isinstance(curve, list)
    assert len(curve) == 5
    cps = [p["correlation_preserve"] for p in curve]
    assert cps == sorted(cps)


@settings(max_examples=15, deadline=None)
@given(st.integers(min_value=1, max_value=200))
def test_property_output_row_count_equals_request(n_samples: int) -> None:
    real = _real(50, 2)
    out = synthesise_trajectories(real, n_samples=n_samples)
    assert out.shape[0] == n_samples
