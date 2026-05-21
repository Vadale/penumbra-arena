"""Causal inference: IPW + AIPW doubly-robust ATE estimators.

Concept taught: regression alone cannot estimate causal effects unless
you've explicitly accounted for the *assignment mechanism* — which
units were treated and why. Three canonical paths:

1. **Propensity score** — fit p(T=1 | X). The classical Rosenbaum-
   Rubin (1983) result: under unconfoundedness, units with the same
   propensity score are exchangeable across the treatment arm.

2. **Inverse Probability Weighting (IPW)** — reweight units by
   1/p̂ in the treated arm and 1/(1-p̂) in the control arm. The
   weighted mean difference is an unbiased estimator of the ATE
   *if* the propensity model is correct.

3. **Augmented IPW (AIPW)** — doubly robust. Fits BOTH a propensity
   model AND an outcome model μ(X). Consistent if *either* model is
   correctly specified. The right default.

In Penumbra: estimate the causal effect of "joining a coalition" on
"match-win probability", with the agent's recent trajectory as the
confounder.

References
- Rosenbaum & Rubin, "The central role of the propensity score in
  observational studies for causal effects" (Biometrika 1983).
- Robins, Rotnitzky, Zhao, "Estimation of regression coefficients
  when some regressors are not always observed" (JASA 1994).
- Hernán & Robins, "Causal Inference: What If" (2020), online book.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sklearn.linear_model import LogisticRegression, Ridge


@dataclass(frozen=True, slots=True)
class CausalEstimate:
    """Estimated Average Treatment Effect with a bootstrap-style SE."""

    ate: float
    se: float
    method: str


def estimate_propensity(
    treatment: NDArray[np.int_],
    covariates: NDArray[np.float64],
    *,
    clip: float = 0.05,
) -> NDArray[np.float64]:
    """Fit p(T=1 | X) via logistic regression; clip away from 0/1.

    Clipping (`clip = 0.05` → score ∈ [0.05, 0.95]) prevents the IPW
    weights from blowing up on units near the support boundary.
    """
    if treatment.ndim != 1 or covariates.ndim != 2:
        raise ValueError("treatment must be 1-D and covariates 2-D")
    if treatment.shape[0] != covariates.shape[0]:
        raise ValueError("treatment and covariates must have the same number of rows")
    if not 0.0 < clip < 0.5:
        raise ValueError("clip must be in (0, 0.5)")
    model = LogisticRegression(max_iter=200)
    model.fit(covariates, treatment)
    probabilities = model.predict_proba(covariates)[:, 1]
    return np.clip(probabilities, clip, 1.0 - clip)


def ipw_ate(
    outcome: NDArray[np.float64],
    treatment: NDArray[np.int_],
    propensity: NDArray[np.float64],
) -> CausalEstimate:
    """IPW estimator of the Average Treatment Effect.

    ATE = E[Y · T / p̂ - Y · (1 - T) / (1 - p̂)]
    Standard error from the per-unit influence function.
    """
    if outcome.shape != treatment.shape or outcome.shape != propensity.shape:
        raise ValueError("outcome, treatment and propensity must align")
    influence = outcome * treatment / propensity - outcome * (1 - treatment) / (1 - propensity)
    ate = float(np.mean(influence))
    se = float(np.std(influence, ddof=1) / np.sqrt(influence.size))
    return CausalEstimate(ate=ate, se=se, method="IPW")


def aipw_ate(
    outcome: NDArray[np.float64],
    treatment: NDArray[np.int_],
    covariates: NDArray[np.float64],
    *,
    clip: float = 0.05,
) -> CausalEstimate:
    """Augmented IPW (doubly robust). Consistent if EITHER model is right.

    The AIPW influence function:
       φ_i = (T_i (Y_i - μ_1(X_i))) / p̂(X_i)
           - ((1 - T_i)(Y_i - μ_0(X_i))) / (1 - p̂(X_i))
           + μ_1(X_i) - μ_0(X_i)
    ATE = mean(φ); SE = std(φ) / √n.
    """
    if outcome.shape != treatment.shape or outcome.shape[0] != covariates.shape[0]:
        raise ValueError("outcome, treatment, covariates must align on rows")
    propensity = estimate_propensity(treatment, covariates, clip=clip)

    mu_1 = Ridge(alpha=1.0).fit(covariates[treatment == 1], outcome[treatment == 1])
    mu_0 = Ridge(alpha=1.0).fit(covariates[treatment == 0], outcome[treatment == 0])
    pred_1 = mu_1.predict(covariates)
    pred_0 = mu_0.predict(covariates)

    influence = (
        treatment * (outcome - pred_1) / propensity
        - (1 - treatment) * (outcome - pred_0) / (1 - propensity)
        + (pred_1 - pred_0)
    )
    ate = float(np.mean(influence))
    se = float(np.std(influence, ddof=1) / np.sqrt(influence.size))
    return CausalEstimate(ate=ate, se=se, method="AIPW")
