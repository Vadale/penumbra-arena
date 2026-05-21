"""Survival analysis: Kaplan-Meier + Cox proportional hazards.

Concept taught: "time until event" data is special — many subjects are
*censored* (we know they survived at least up to time T but not when
they die). Naive regression drops the censored rows and biases
everything. Survival analysis handles censoring natively.

In Penumbra we model "time until an agent is eliminated" — agents who
haven't been eliminated yet by the end of a match are censored.

References
- Kaplan & Meier, "Nonparametric estimation from incomplete
  observations" (JASA 1958).
- Cox, "Regression models and life-tables" (JRSS-B 1972).
- lifelines: https://lifelines.readthedocs.io/
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from lifelines import CoxPHFitter, KaplanMeierFitter
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class KMSurvivalCurve:
    """Non-parametric KM survival curve at the input event times."""

    times: NDArray[np.float64]
    survival: NDArray[np.float64]
    confidence_low: NDArray[np.float64]
    confidence_high: NDArray[np.float64]


def kaplan_meier(
    durations: NDArray[np.float64],
    events: NDArray[np.bool_],
) -> KMSurvivalCurve:
    """Fit a KM survival curve. `events[i]=True` means subject i died."""
    if durations.shape != events.shape:
        raise ValueError("durations and events must align")
    fitter = KaplanMeierFitter()
    fitter.fit(durations=durations, event_observed=events.astype(int))
    times = np.asarray(fitter.survival_function_.index, dtype=np.float64)
    survival = np.asarray(fitter.survival_function_.values.ravel(), dtype=np.float64)
    ci = fitter.confidence_interval_
    return KMSurvivalCurve(
        times=times,
        survival=survival,
        confidence_low=np.asarray(ci.iloc[:, 0].values, dtype=np.float64),
        confidence_high=np.asarray(ci.iloc[:, 1].values, dtype=np.float64),
    )


@dataclass(frozen=True, slots=True)
class CoxModelResult:
    hazard_ratios: dict[str, float]
    p_values: dict[str, float]
    concordance: float


def cox_proportional_hazards(
    durations: NDArray[np.float64],
    events: NDArray[np.bool_],
    covariates: dict[str, NDArray[np.float64]],
) -> CoxModelResult:
    """Fit a Cox PH model relating per-subject covariates to hazard rate.

    Hazard ratio > 1 means the covariate accelerates failure; < 1
    means it protects.
    """
    import pandas as pd

    if durations.shape != events.shape:
        raise ValueError("durations and events must align")
    for name, vec in covariates.items():
        if vec.shape != durations.shape:
            raise ValueError(f"covariate '{name}' must align with durations")
    frame = pd.DataFrame(
        {
            "duration": durations,
            "event": events.astype(int),
            **covariates,
        }
    )
    fitter = CoxPHFitter()
    fitter.fit(frame, duration_col="duration", event_col="event")
    hazard_ratios = {name: float(np.exp(fitter.params_[name])) for name in covariates}
    p_values = {name: float(fitter.summary.loc[name, "p"]) for name in covariates}
    return CoxModelResult(
        hazard_ratios=hazard_ratios,
        p_values=p_values,
        concordance=float(fitter.concordance_index_),
    )
