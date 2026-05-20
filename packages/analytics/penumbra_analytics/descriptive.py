"""Descriptive statistics via Polars + NumPy.

Concept taught: descriptive stats are the first pass on any new dataset.
The point isn't just to compute mean and std — it's to *characterise*
the shape: central tendency, dispersion, skewness, tail weight, and to
quantify uncertainty via confidence intervals.

Penumbra streams trajectories (per-tick per-agent positions) and match
outcomes (winner, end-tick, end-reason). This module operates on each.

Reference: Wilcox, "Introduction to Robust Estimation and Hypothesis
Testing" (2017) — for the case against the naive mean.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl
from numpy.typing import NDArray
from scipy.stats import bootstrap as scipy_bootstrap


@dataclass(frozen=True, slots=True)
class Summary:
    """Robust summary of a 1-D numeric sample.

    Includes the trimmed mean and IQR alongside the classical mean and
    std so the user can compare robustness side by side.
    """

    n: int
    mean: float
    std: float
    median: float
    iqr: float
    trimmed_mean_10: float
    skewness: float
    excess_kurtosis: float
    min: float
    max: float
    ci95_low: float
    ci95_high: float


def summarise(values: NDArray[np.float64], *, n_resamples: int = 999) -> Summary:
    """Build a robust Summary of `values`.

    `ci95_*` is a non-parametric bootstrap CI for the mean; for an
    n=1000 vector with default n_resamples this takes <10ms on M4.
    """
    if values.ndim != 1:
        raise ValueError("descriptive.summarise expects a 1-D vector")
    if values.size == 0:
        raise ValueError("cannot summarise an empty vector")
    rng = np.random.default_rng(seed=0)
    boot = scipy_bootstrap(
        (values,),
        statistic=np.mean,
        n_resamples=n_resamples,
        confidence_level=0.95,
        method="basic",
        random_state=rng,  # pyright: ignore[reportCallIssue]
    )
    return Summary(
        n=int(values.size),
        mean=float(np.mean(values)),
        std=float(np.std(values, ddof=1)) if values.size > 1 else 0.0,
        median=float(np.median(values)),
        iqr=float(np.subtract(*np.percentile(values, [75, 25]))),
        trimmed_mean_10=_trimmed_mean(values, 0.10),
        skewness=_skewness(values),
        excess_kurtosis=_excess_kurtosis(values),
        min=float(np.min(values)),
        max=float(np.max(values)),
        ci95_low=float(boot.confidence_interval.low),
        ci95_high=float(boot.confidence_interval.high),
    )


def by_group(frame: pl.DataFrame, *, value_col: str, group_col: str) -> pl.DataFrame:
    """Polars-native per-group descriptive table. Lazy-friendly."""
    return (
        frame.lazy()
        .group_by(group_col)
        .agg(
            pl.col(value_col).count().alias("n"),
            pl.col(value_col).mean().alias("mean"),
            pl.col(value_col).std().alias("std"),
            pl.col(value_col).median().alias("median"),
            pl.col(value_col).quantile(0.25).alias("q25"),
            pl.col(value_col).quantile(0.75).alias("q75"),
            pl.col(value_col).min().alias("min"),
            pl.col(value_col).max().alias("max"),
        )
        .sort(group_col)
        .collect()
    )


def _trimmed_mean(values: NDArray[np.float64], proportion: float) -> float:
    """Symmetric two-tail trimmed mean."""
    if not 0.0 <= proportion < 0.5:
        raise ValueError("trim proportion must be in [0, 0.5)")
    sorted_v = np.sort(values)
    k = int(np.floor(proportion * sorted_v.size))
    return float(np.mean(sorted_v[k : sorted_v.size - k])) if sorted_v.size - 2 * k > 0 else 0.0


def _skewness(values: NDArray[np.float64]) -> float:
    if values.size < 3:
        return 0.0
    m = float(np.mean(values))
    s = float(np.std(values, ddof=1))
    if s == 0:
        return 0.0
    return float(np.mean(((values - m) / s) ** 3))


def _excess_kurtosis(values: NDArray[np.float64]) -> float:
    if values.size < 4:
        return 0.0
    m = float(np.mean(values))
    s = float(np.std(values, ddof=1))
    if s == 0:
        return 0.0
    return float(np.mean(((values - m) / s) ** 4) - 3.0)
