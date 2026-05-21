"""Bayesian inference via NumPyro stochastic variational inference.

Concept taught: when you can't enumerate all hypotheses analytically,
*approximate* the posterior. SVI parameterises a family `q(z|φ)` of
distributions, then optimises `φ` to minimise KL(q || posterior). On
M4 this is sub-second; full MCMC would be 100x slower.

The canonical Penumbra use is: given DP-noised aggregate statistics
of agent positions, infer the posterior over a tracked agent's
*region*. Here we expose the primitive — a beta-binomial posterior
under SVI — as a small worked example.

References
- Kingma & Welling, "Auto-Encoding Variational Bayes" (ICLR 2014):
  the modern resurrection of variational inference.
- NumPyro: https://num.pyro.ai/
"""

from __future__ import annotations

from dataclasses import dataclass

import jax
import jax.numpy as jnp
import numpy as np
import numpyro
import numpyro.distributions as dist
from numpy.typing import NDArray
from numpyro.infer import SVI, Trace_ELBO
from numpyro.infer.autoguide import AutoNormal


@dataclass(frozen=True, slots=True)
class PosteriorEstimate:
    """Mean + std of the inferred posterior parameter."""

    mean: float
    std: float
    n_iters: int


def beta_binomial_posterior(
    successes: int,
    trials: int,
    *,
    n_iters: int = 1_000,
    seed: int = 0,
) -> PosteriorEstimate:
    """Infer the success probability θ ∈ [0, 1] from a beta-binomial likelihood.

    Prior: Beta(1, 1) (uniform). Likelihood: Binomial(trials, θ).
    SVI guide: a normal distribution on logit(θ), reparameterised
    through a sigmoid at observation time.
    """
    if successes < 0 or trials <= 0 or successes > trials:
        raise ValueError("require 0 ≤ successes ≤ trials and trials > 0")

    def model() -> None:
        theta = numpyro.sample("theta", dist.Beta(1.0, 1.0))
        numpyro.sample("obs", dist.Binomial(total_count=trials, probs=theta), obs=successes)

    guide = AutoNormal(model)
    svi = SVI(model, guide, numpyro.optim.Adam(0.05), Trace_ELBO())
    key = jax.random.PRNGKey(seed)
    result = svi.run(key, n_iters, progress_bar=False)
    params = result.params
    posterior_samples = guide.sample_posterior(
        jax.random.PRNGKey(seed + 1), params, sample_shape=(2_000,)
    )
    theta = np.asarray(posterior_samples["theta"])  # type: ignore[index]
    return PosteriorEstimate(
        mean=float(theta.mean()),
        std=float(theta.std()),
        n_iters=n_iters,
    )


def linear_regression_posterior(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    *,
    n_iters: int = 1_500,
    seed: int = 0,
) -> dict[str, PosteriorEstimate]:
    """Bayesian linear regression y = α + β·x + ε via SVI.

    Returns a posterior estimate for both α (intercept) and β (slope).
    """
    if x.shape != y.shape or x.ndim != 1:
        raise ValueError("x and y must be 1-D and aligned")
    x_jax = jnp.asarray(x, dtype=jnp.float32)
    y_jax = jnp.asarray(y, dtype=jnp.float32)

    def model() -> None:
        alpha = numpyro.sample("alpha", dist.Normal(0.0, 10.0))
        beta = numpyro.sample("beta", dist.Normal(0.0, 10.0))
        sigma = numpyro.sample("sigma", dist.HalfNormal(5.0))
        mean = alpha + beta * x_jax
        numpyro.sample("obs", dist.Normal(mean, sigma), obs=y_jax)

    guide = AutoNormal(model)
    svi = SVI(model, guide, numpyro.optim.Adam(0.05), Trace_ELBO())
    key = jax.random.PRNGKey(seed)
    result = svi.run(key, n_iters, progress_bar=False)
    samples = guide.sample_posterior(
        jax.random.PRNGKey(seed + 1), result.params, sample_shape=(2_000,)
    )
    alpha_samples = np.asarray(samples["alpha"])  # type: ignore[index]
    beta_samples = np.asarray(samples["beta"])  # type: ignore[index]
    return {
        "alpha": PosteriorEstimate(
            mean=float(alpha_samples.mean()),
            std=float(alpha_samples.std()),
            n_iters=n_iters,
        ),
        "beta": PosteriorEstimate(
            mean=float(beta_samples.mean()),
            std=float(beta_samples.std()),
            n_iters=n_iters,
        ),
    }
