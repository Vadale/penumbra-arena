"""Correlation-preserving synthetic-trace release (GAN stub).

Concept taught: instead of releasing raw trajectories, release samples
from a generative model fitted to the distribution. The privacy benefit
is that no released sample corresponds to any single training record;
the utility cost is the gap between the model's marginals + correlations
and the empirical ones.

Phase 5 Tier 3 ships a *Gaussian* stub: fit the empirical mean +
covariance of a real trajectory feature matrix and sample from the
matching multivariate-normal. This preserves first + second-order
statistics by construction (mean, variance, pairwise correlations)
and intentionally destroys everything else. A real CycleGAN / time-series
GAN (TimeGAN, DoppelGANger) is deferred — same API surface, drop-in
replacement.

API is pure-functional:

    synth = synthesise_trajectories(real_features, n_samples=N)

The returned ``(n_samples, n_features)`` matrix has, in expectation,
the same mean + covariance as the input. Two utility metrics quantify
the fidelity: ``mean_l2`` and ``cov_frobenius`` differences.

Privacy headline: every released sample is a fresh draw — no membership
inference adversary can score above chance on the trained model's
output (it has never seen the real records). The remaining leakage is
through the model's *parameters* (mean + covariance) which we expose
explicitly so the user understands what the GAN is "remembering".

References
----------
- Goodfellow et al. "Generative Adversarial Nets" (NeurIPS 2014).
- Yoon et al. "TimeGAN" (NeurIPS 2019) — the trajectory-friendly
  variant we'd plug in to replace this stub.
- Jordon et al. "PATE-GAN" (ICLR 2019) — DP-GAN, the privacy-aware
  upgrade path.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(slots=True, frozen=True)
class SyntheticReport:
    """Privacy-utility tradeoff snapshot for a synthetic-release pass."""

    n_real: int
    n_synth: int
    n_features: int
    mean_l2: float
    cov_frobenius: float
    privacy_membership_advantage: float


def _secure_rng() -> np.random.Generator:
    seed = int.from_bytes(secrets.token_bytes(8), "big")
    return np.random.default_rng(seed)


def _validate_matrix(matrix: NDArray[np.float64]) -> None:
    if matrix.ndim != 2:
        raise GANDefenseError(f"matrix must be 2-D, got ndim={matrix.ndim}")
    if matrix.shape[0] < 2:
        raise GANDefenseError("matrix must have ≥ 2 rows to estimate covariance")
    if matrix.shape[1] < 1:
        raise GANDefenseError("matrix must have ≥ 1 column")
    if not np.isfinite(matrix).all():
        raise GANDefenseError("matrix must contain only finite values")


def fit_gaussian_model(
    real_features: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return ``(mean, covariance)`` of ``real_features`` along axis 0.

    The covariance is the unbiased (n-1) estimator. A tiny diagonal
    ridge is added so the sampler never sees a singular matrix on
    rank-deficient inputs (a common failure mode on small feature
    matrices).
    """
    _validate_matrix(real_features)
    mu = real_features.mean(axis=0)
    cov = np.cov(real_features, rowvar=False)
    cov = np.atleast_2d(cov)
    ridge = 1e-9 * np.eye(cov.shape[0])
    return mu, cov + ridge


def synthesise_trajectories(
    real_features: NDArray[np.float64],
    n_samples: int,
    *,
    correlation_preserve: float = 1.0,
    rng: np.random.Generator | None = None,
) -> NDArray[np.float64]:
    """Sample ``n_samples`` rows from a Gaussian fit to ``real_features``.

    ``correlation_preserve ∈ [0, 1]`` interpolates between independent
    Gaussian noise (0.0 — destroys correlations, max privacy on the
    correlation channel) and the full empirical covariance (1.0 —
    preserves all pairwise correlations). Real-GAN replacements will
    expose the same knob as a temperature / quality parameter.
    """
    if n_samples <= 0:
        raise GANDefenseError(f"n_samples must be > 0, got {n_samples}")
    if not 0.0 <= correlation_preserve <= 1.0:
        raise GANDefenseError(f"correlation_preserve must be in [0, 1], got {correlation_preserve}")
    rng = rng if rng is not None else _secure_rng()
    mu, cov = fit_gaussian_model(real_features)
    diag = np.diag(np.diag(cov))
    blended = correlation_preserve * cov + (1.0 - correlation_preserve) * diag
    return rng.multivariate_normal(mean=mu, cov=blended, size=n_samples)


def evaluate_tradeoff(
    real_features: NDArray[np.float64],
    n_samples: int,
    *,
    correlation_preserve: float = 1.0,
    rng: np.random.Generator | None = None,
) -> SyntheticReport:
    """Quantify the privacy-utility tradeoff of a synthetic release.

    Utility: L2 distance between real and synthetic means + Frobenius
    distance between covariances. Privacy: ``privacy_membership_advantage``
    is fixed at 0.0 here — every output is a fresh draw from the model,
    so a membership-inference adversary on the OUTPUT scores at chance.
    The model PARAMETERS (mu, cov) still leak; we'd compose with DP-SGD
    on the fit to bound that channel.
    """
    rng = rng if rng is not None else _secure_rng()
    synth = synthesise_trajectories(
        real_features,
        n_samples,
        correlation_preserve=correlation_preserve,
        rng=rng,
    )
    real_mu = real_features.mean(axis=0)
    real_cov = np.atleast_2d(np.cov(real_features, rowvar=False))
    synth_mu = synth.mean(axis=0)
    synth_cov = np.atleast_2d(np.cov(synth, rowvar=False))
    return SyntheticReport(
        n_real=int(real_features.shape[0]),
        n_synth=int(synth.shape[0]),
        n_features=int(real_features.shape[1]),
        mean_l2=float(np.linalg.norm(real_mu - synth_mu)),
        cov_frobenius=float(np.linalg.norm(real_cov - synth_cov)),
        privacy_membership_advantage=0.0,
    )


def demo() -> dict[str, object]:
    """Self-contained demo: sweep ``correlation_preserve`` and report metrics."""
    rng = np.random.default_rng(seed=20260523)
    n_real = 256
    n_features = 4
    # A real-looking trajectory feature matrix with non-trivial correlations.
    base = rng.standard_normal(size=(n_real, n_features))
    mixer = np.array(
        [
            [1.0, 0.6, 0.0, 0.2],
            [0.6, 1.0, 0.3, 0.1],
            [0.0, 0.3, 1.0, 0.4],
            [0.2, 0.1, 0.4, 1.0],
        ]
    )
    real = base @ mixer.T
    curve: list[dict[str, float]] = []
    for cp in (0.0, 0.25, 0.5, 0.75, 1.0):
        report = evaluate_tradeoff(
            real, n_samples=512, correlation_preserve=cp, rng=np.random.default_rng(seed=42)
        )
        curve.append(
            {
                "correlation_preserve": float(cp),
                "mean_l2": report.mean_l2,
                "cov_frobenius": report.cov_frobenius,
                "privacy_membership_advantage": report.privacy_membership_advantage,
            }
        )
    return {
        "available": True,
        "algorithm": "Gaussian synthetic-trace stub (CycleGAN deferred)",
        "n_real": n_real,
        "n_features": n_features,
        "curve": curve,
    }


class GANDefenseError(ValueError):
    """Raised on invalid synthetic-release parameters."""
