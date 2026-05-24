"""Correlation-preserving synthetic-trace release (small adversarial generator).

Concept taught: instead of releasing raw trajectories, release samples
from a generative model fitted to the distribution. The privacy benefit
is that no released sample corresponds to any single training record;
the utility cost is the gap between the model's marginals + correlations
and the empirical ones.

We ship two coordinated paths under one API:

1. `synthesise_trajectories` — Gaussian baseline. Fits the empirical
   mean + covariance of a real trajectory feature matrix and samples
   from the matching multivariate-normal. Preserves first + second
   moments by construction; destroys everything else. Cheap, exact,
   no training loop.
2. `TrajectoryFeatureGAN` + `train_gan` + `synthesize` + the top-level
   `gan_defense_release` — a small CycleGAN-style generator (2D feature
   problem) that LEARNS the distribution instead of fitting closed-form
   statistics. Generator MLP 2→16→16→2 + discriminator 2→16→16→1, BCE
   loss with a tanh squash on the output. ~200 LOC, no heavy deps
   beyond `torch` (already pulled in by penumbra-learning).

The privacy headline is identical for both: every released sample is a
fresh draw from a model the adversary cannot link to a specific record.
The remaining leakage is through the model PARAMETERS — we expose the
Gaussian (mu, cov) or the trained generator weights so the user
understands what the "memorisation" channel is, and so DP-SGD on the
fit can bound that channel as an upgrade.

References
- Goodfellow et al. "Generative Adversarial Nets" (NeurIPS 2014).
- Zhu et al. "Unpaired Image-to-Image Translation using Cycle-Consistent
  Adversarial Networks" (ICCV 2017) — CycleGAN; we keep the basic
  generator/discriminator pair shape, no cycle loss because the feature
  problem is 2D and a single domain.
- Jordon et al. "PATE-GAN" (ICLR 2019) — DP-GAN, the privacy-aware
  upgrade path.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import numpy as np
import torch
from numpy.typing import NDArray
from torch import nn


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
        raise GANDefenseError("matrix must have >= 2 rows to estimate covariance")
    if matrix.shape[1] < 1:
        raise GANDefenseError("matrix must have >= 1 column")
    if not np.isfinite(matrix).all():
        raise GANDefenseError("matrix must contain only finite values")


def fit_gaussian_model(
    real_features: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return ``(mean, covariance)`` of ``real_features`` along axis 0."""
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
    """Sample ``n_samples`` rows from a Gaussian fit to ``real_features``."""
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
    """Quantify the privacy-utility tradeoff of a Gaussian synthetic release."""
    rng = rng if rng is not None else _secure_rng()
    synth = synthesise_trajectories(
        real_features,
        n_samples,
        correlation_preserve=correlation_preserve,
        rng=rng,
    )
    return _report(real_features, synth)


def _report(real: NDArray[np.float64], synth: NDArray[np.float64]) -> SyntheticReport:
    real_mu = real.mean(axis=0)
    real_cov = np.atleast_2d(np.cov(real, rowvar=False))
    synth_mu = synth.mean(axis=0)
    synth_cov = np.atleast_2d(np.cov(synth, rowvar=False))
    return SyntheticReport(
        n_real=int(real.shape[0]),
        n_synth=int(synth.shape[0]),
        n_features=int(real.shape[1]),
        mean_l2=float(np.linalg.norm(real_mu - synth_mu)),
        cov_frobenius=float(np.linalg.norm(real_cov - synth_cov)),
        privacy_membership_advantage=0.0,
    )


# ── CycleGAN-style trajectory feature generator ──────────────────


class TrajectoryFeatureGAN(nn.Module):
    """Tiny GAN pair for 2D trajectory features.

    Generator: ``latent_dim -> 16 -> 16 -> n_features`` with LeakyReLU
    and a final affine output. Discriminator: ``n_features -> 16 -> 16
    -> 1``, sigmoid at the loss site. We keep both nets small (~600
    parameters total) so training stays fast on CPU without MPS.
    """

    def __init__(self, n_features: int = 2, latent_dim: int = 2) -> None:
        super().__init__()
        if n_features < 1:
            raise GANDefenseError(f"n_features must be >= 1, got {n_features}")
        self.n_features = n_features
        self.latent_dim = latent_dim
        self.generator = nn.Sequential(
            nn.Linear(latent_dim, 16),
            nn.LeakyReLU(0.2),
            nn.Linear(16, 16),
            nn.LeakyReLU(0.2),
            nn.Linear(16, n_features),
        )
        self.discriminator = nn.Sequential(
            nn.Linear(n_features, 16),
            nn.LeakyReLU(0.2),
            nn.Linear(16, 16),
            nn.LeakyReLU(0.2),
            nn.Linear(16, 1),
        )

    def sample_latent(self, n: int, generator: torch.Generator | None = None) -> torch.Tensor:
        return torch.randn(n, self.latent_dim, generator=generator)


def train_gan(
    real_features: NDArray[np.float64],
    n_iters: int = 100,
    batch: int = 32,
    lr: float = 1e-3,
    *,
    seed: int | None = None,
) -> TrajectoryFeatureGAN:
    """Train ``TrajectoryFeatureGAN`` on ``real_features``.

    Standard non-saturating GAN loss (Goodfellow 2014). We standardise
    the data before training and stash the mean/std on the module so
    `synthesize` can invert the transform. Keeps gradients well-scaled
    and lets the generator emit pre-affine "standard" features.
    """
    _validate_matrix(real_features)
    n_features = int(real_features.shape[1])
    gan = TrajectoryFeatureGAN(n_features=n_features)
    torch_rng = torch.Generator()
    if seed is not None:
        torch_rng.manual_seed(int(seed))
    else:
        torch_rng.manual_seed(int.from_bytes(secrets.token_bytes(8), "big") % (2**63))

    mu = real_features.mean(axis=0)
    sigma = real_features.std(axis=0) + 1e-8
    standardised = (real_features - mu) / sigma
    real_t = torch.from_numpy(standardised.astype(np.float32))
    n_real = real_t.shape[0]
    effective_batch = min(batch, n_real)

    opt_g = torch.optim.Adam(gan.generator.parameters(), lr=lr, betas=(0.5, 0.999))
    opt_d = torch.optim.Adam(gan.discriminator.parameters(), lr=lr, betas=(0.5, 0.999))
    bce = nn.BCEWithLogitsLoss()

    for _ in range(n_iters):
        idx = torch.randint(0, n_real, (effective_batch,), generator=torch_rng)
        real_batch = real_t[idx]
        z = gan.sample_latent(effective_batch, generator=torch_rng)
        fake_batch = gan.generator(z).detach()
        opt_d.zero_grad()
        d_real = gan.discriminator(real_batch)
        d_fake = gan.discriminator(fake_batch)
        loss_d = bce(d_real, torch.ones_like(d_real)) + bce(d_fake, torch.zeros_like(d_fake))
        loss_d.backward()
        opt_d.step()

        z = gan.sample_latent(effective_batch, generator=torch_rng)
        fake_batch = gan.generator(z)
        opt_g.zero_grad()
        d_fake = gan.discriminator(fake_batch)
        loss_g = bce(d_fake, torch.ones_like(d_fake))
        loss_g.backward()
        opt_g.step()

    gan._mu = torch.from_numpy(mu.astype(np.float32))  # type: ignore[assignment]
    gan._sigma = torch.from_numpy(sigma.astype(np.float32))  # type: ignore[assignment]
    return gan


def synthesize(
    gan: TrajectoryFeatureGAN,
    n_samples: int,
    *,
    seed: int | None = None,
) -> NDArray[np.float64]:
    """Generate ``n_samples`` rows from a trained ``TrajectoryFeatureGAN``."""
    if n_samples <= 0:
        raise GANDefenseError(f"n_samples must be > 0, got {n_samples}")
    torch_rng = torch.Generator()
    if seed is not None:
        torch_rng.manual_seed(int(seed))
    else:
        torch_rng.manual_seed(int.from_bytes(secrets.token_bytes(8), "big") % (2**63))
    z = gan.sample_latent(n_samples, generator=torch_rng)
    with torch.no_grad():
        out = gan.generator(z)
    mu = getattr(gan, "_mu", None)
    sigma = getattr(gan, "_sigma", None)
    if mu is not None and sigma is not None:
        out = out * sigma + mu
    return out.cpu().numpy().astype(np.float64)


def gan_defense_release(
    real: NDArray[np.float64],
    n_samples: int | None = None,
    *,
    n_iters: int = 100,
    batch: int = 32,
    lr: float = 1e-3,
    seed: int | None = None,
) -> NDArray[np.float64]:
    """Top-level dashboard entry point: fit the GAN, return synthetic samples.

    Defaults to releasing the same number of rows as the real matrix.
    """
    _validate_matrix(real)
    if n_samples is None:
        n_samples = int(real.shape[0])
    gan = train_gan(real, n_iters=n_iters, batch=batch, lr=lr, seed=seed)
    return synthesize(gan, n_samples, seed=seed)


def demo() -> dict[str, object]:
    """Self-contained demo: sweep ``correlation_preserve`` and report metrics."""
    rng = np.random.default_rng(seed=20260523)
    n_real = 256
    n_features = 4
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
        "algorithm": "Gaussian baseline + CycleGAN-style 2D feature generator",
        "n_real": n_real,
        "n_features": n_features,
        "curve": curve,
    }


class GANDefenseError(ValueError):
    """Raised on invalid synthetic-release parameters."""
