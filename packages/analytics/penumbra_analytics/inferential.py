"""Inferential statistics.

Concept taught: the right test is *not* always the t-test. When samples
aren't normally distributed, when variances differ, when categorical
counts beg comparison, the textbook recipe is different. This module
exposes the workhorse non-parametric and resampling tests that handle
real-world data without normality assumptions.

References
- Wilcox, "Introduction to Robust Estimation and Hypothesis Testing"
  (2017), chapters 4–7.
- Good, "Permutation, Parametric, and Bootstrap Tests of Hypotheses"
  (2005).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.stats import chisquare, mannwhitneyu


@dataclass(frozen=True, slots=True)
class TestResult:
    """A scalar test statistic + p-value + decision at α=0.05."""

    statistic: float
    p_value: float
    reject_at_05: bool
    test: str


def mann_whitney(a: NDArray[np.float64], b: NDArray[np.float64]) -> TestResult:
    """Mann-Whitney U: non-parametric two-sample location test.

    H_0: P(X > Y) = P(Y > X). Robust against non-normality; the right
    default when you don't know the distribution shape. Two-sided by
    convention; pass `alternative` to scipy yourself if you need one-
    sided power.
    """
    stat, p = mannwhitneyu(a, b, alternative="two-sided")
    return TestResult(
        statistic=float(stat),
        p_value=float(p),
        reject_at_05=bool(p < 0.05),
        test="mann_whitney_u",
    )


def permutation(
    a: NDArray[np.float64],
    b: NDArray[np.float64],
    *,
    n_perm: int = 9_999,
    seed: int | None = None,
) -> TestResult:
    """Two-sided permutation test for difference in means.

    Distribution-free: simply enumerate (or randomly sample) all
    relabelings of A ∪ B and compute the fraction with a |mean diff|
    at least as extreme as the observed. Honest small-sample p-value.
    """
    rng = np.random.default_rng(seed)
    pooled = np.concatenate([a, b])
    observed = abs(np.mean(a) - np.mean(b))
    extreme = 0
    n_a = a.size
    for _ in range(n_perm):
        perm = rng.permutation(pooled)
        diff = abs(np.mean(perm[:n_a]) - np.mean(perm[n_a:]))
        if diff >= observed:
            extreme += 1
    # +1 in numerator and denominator avoids a p=0 artefact.
    p = (extreme + 1) / (n_perm + 1)
    return TestResult(
        statistic=float(observed),
        p_value=float(p),
        reject_at_05=bool(p < 0.05),
        test="permutation_mean",
    )


def chi_squared_goodness_of_fit(
    observed: NDArray[np.float64],
    expected: NDArray[np.float64],
) -> TestResult:
    """χ² test that an observed count vector follows the expected distribution.

    Each bin's expected count should be ≥ 5 for the asymptotic χ²
    approximation to be accurate; otherwise consider a permutation
    alternative.
    """
    if observed.shape != expected.shape:
        raise ValueError("observed and expected must have the same shape")
    stat, p = chisquare(f_obs=observed, f_exp=expected)
    return TestResult(
        statistic=float(stat),
        p_value=float(p),
        reject_at_05=bool(p < 0.05),
        test="chi_squared",
    )


def cliff_delta(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    """Cliff's δ: a robust effect size in [-1, 1].

    Probability that a random A exceeds a random B, minus the
    probability of the reverse. Complements Mann-Whitney: U tells you
    if the difference is significant, δ tells you how large it is.
    """
    n_a = a.size
    n_b = b.size
    if n_a == 0 or n_b == 0:
        raise ValueError("Cliff's delta requires non-empty samples")
    greater = sum(int(x > y) for x in a for y in b)
    less = sum(int(x < y) for x in a for y in b)
    return float((greater - less) / (n_a * n_b))
