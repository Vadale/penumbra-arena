"""Monte Carlo: Sobol quasi-MC, bootstrap, VaR / CVaR.

Concept taught: when you can't get a closed form, you sample. The
right *kind* of sampling matters: independent uniform draws (classic
MC) converge at √n; low-discrepancy sequences like Sobol converge at
≈ (log n)^d / n for smooth integrands, which is dramatically faster in
low dimensions.

Penumbra uses Monte Carlo to forecast match-outcome distributions
(what's the probability validator V wins the next match?) and to size
"reserve" amounts via VaR / CVaR over agent-trajectory length.

References
- Niederreiter, "Random Number Generation and Quasi-Monte Carlo
  Methods" (1992).
- Owen, "Monte Carlo theory, methods and examples" (2013), online.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.stats import bootstrap as scipy_bootstrap
from scipy.stats.qmc import Sobol


def sobol_sample(
    dimensions: int, n_points: int, *, scramble: bool = True, seed: int = 0
) -> NDArray[np.float64]:
    """Generate `n_points` Sobol points in [0,1]^dimensions.

    n_points should be a power of 2 for the canonical Sobol guarantee.
    Scrambling (Owen) is on by default — it preserves the low-
    discrepancy property and gives a usable bootstrap variance estimate.
    """
    if dimensions < 1:
        raise ValueError("dimensions must be >= 1")
    sampler = Sobol(d=dimensions, scramble=scramble, seed=seed)  # pyright: ignore[reportCallIssue]
    return np.asarray(sampler.random(n=n_points), dtype=np.float64)


def integrate(
    f: Callable[[NDArray[np.float64]], NDArray[np.float64]],
    dimensions: int,
    *,
    n_points: int = 4_096,
    seed: int = 0,
) -> tuple[float, float]:
    """Quasi-MC integral of f over the unit cube. Returns (estimate, std_err).

    Standard error is computed via independent batch means — split the
    Sobol points into 32 batches, take each batch's average, and the
    sample std of those.
    """
    pts = sobol_sample(dimensions, n_points, seed=seed)
    vals = f(pts)
    if vals.shape != (n_points,):
        raise ValueError(f"f must return shape ({n_points},); got {vals.shape}")
    batches = vals.reshape(32, -1).mean(axis=1)
    return float(np.mean(vals)), float(np.std(batches, ddof=1) / np.sqrt(32))


@dataclass(frozen=True, slots=True)
class RiskMetrics:
    """Tail-risk summary at a given confidence level."""

    confidence: float
    var: float  # Value-at-Risk: the (1-α) quantile of losses
    cvar: float  # Expected shortfall: average loss beyond VaR


def var_cvar(losses: NDArray[np.float64], *, confidence: float = 0.95) -> RiskMetrics:
    """Empirical VaR and CVaR at the given confidence.

    `losses` are *positive* numbers representing the magnitude of a
    bad outcome; flip signs if your simulation measures rewards.
    """
    if not 0 < confidence < 1:
        raise ValueError("confidence must be in (0, 1)")
    if losses.size == 0:
        raise ValueError("cannot compute VaR on empty sample")
    var = float(np.quantile(losses, confidence))
    tail = losses[losses >= var]
    cvar = float(np.mean(tail)) if tail.size > 0 else var
    return RiskMetrics(confidence=confidence, var=var, cvar=cvar)


def bootstrap_mean(
    sample: NDArray[np.float64],
    *,
    n_resamples: int = 9_999,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """Non-parametric bootstrap CI for the sample mean. Returns (low, high)."""
    rng = np.random.default_rng(seed)
    boot = scipy_bootstrap(
        (sample,),
        statistic=np.mean,
        n_resamples=n_resamples,
        confidence_level=confidence,
        method="basic",
        random_state=rng,  # pyright: ignore[reportCallIssue]
    )
    return float(boot.confidence_interval.low), float(boot.confidence_interval.high)
