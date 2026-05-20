"""Econometrics: OLS with HAC, VAR, Granger causality.

Concept taught: econometric models layered on the simulation. Three
canonical exercises drive everything in this module:

1. **OLS with Newey-West HAC standard errors.** Plain OLS assumes IID
   homoscedastic residuals — never true in a time series. Newey-West
   reweights the asymptotic covariance to absorb autocorrelation and
   heteroscedasticity. We expose both classical and HAC SEs so the
   user can see the difference.

2. **Vector autoregression (VAR).** Joint dynamics of multiple time
   series, each regressed on lags of itself *and* the others.
   Foundation for impulse-response analysis and forecasting.

3. **Granger causality.** Does past X help predict Y *beyond* what
   past Y already predicts? Not causality in the philosophical sense;
   causality in the predictive sense. Penumbra checks whether agent
   activity in one region Granger-causes activity in another.

References
- Newey, West (Econometrica 1987): HAC covariance.
- Lütkepohl, "New Introduction to Multiple Time Series Analysis" (2005).
- Granger, "Investigating causal relations" (Econometrica 1969).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import grangercausalitytests


@dataclass(frozen=True, slots=True)
class OLSResult:
    """OLS coefficients with both classical and HAC standard errors."""

    coefficients: NDArray[np.float64]
    classical_se: NDArray[np.float64]
    hac_se: NDArray[np.float64]
    r_squared: float
    n_obs: int


def ols_with_hac(
    y: NDArray[np.float64],
    x: NDArray[np.float64],
    *,
    hac_lags: int | None = None,
) -> OLSResult:
    """OLS estimation with both classical and Newey-West HAC SEs.

    `x` should NOT include a constant column — we add one ourselves so
    the user doesn't accidentally double-intercept. Default HAC lag is
    Newey-West's rule of thumb: floor(4*(n/100)^{2/9}).
    """
    import statsmodels.api as sm

    if y.ndim != 1:
        raise ValueError("y must be 1-D")
    x_design: NDArray[np.float64] = cast(
        NDArray[np.float64],
        sm.add_constant(x, has_constant="add", prepend=True).astype(np.float64),
    )
    model_fit = sm.OLS(y, x_design).fit()
    classical_se = np.asarray(model_fit.bse, dtype=np.float64)

    n = y.size
    lags = hac_lags if hac_lags is not None else int(np.floor(4 * (n / 100) ** (2 / 9)))
    hac_fit = sm.OLS(y, x_design).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    hac_se = np.asarray(hac_fit.bse, dtype=np.float64)

    return OLSResult(
        coefficients=np.asarray(model_fit.params, dtype=np.float64),
        classical_se=classical_se,
        hac_se=hac_se,
        r_squared=float(model_fit.rsquared),
        n_obs=int(n),
    )


@dataclass(frozen=True, slots=True)
class VARResult:
    """Reduced-form VAR with selected lag order."""

    lag_order: int
    coefficients: NDArray[np.float64]  # shape (lag, n_series, n_series)
    n_series: int
    n_obs: int


def fit_var(series: NDArray[np.float64], *, max_lags: int = 4) -> VARResult:
    """Fit a VAR(p) with lag p chosen by AIC up to `max_lags`."""
    if series.ndim != 2:
        raise ValueError("series must be 2-D (n_obs, n_series)")
    model_fit = VAR(series).fit(maxlags=max_lags, ic="aic")
    coefs = np.asarray(model_fit.coefs, dtype=np.float64)
    return VARResult(
        lag_order=int(model_fit.k_ar),
        coefficients=coefs,
        n_series=int(series.shape[1]),
        n_obs=int(series.shape[0]),
    )


def granger_p_value(
    cause: NDArray[np.float64],
    effect: NDArray[np.float64],
    *,
    max_lag: int = 4,
) -> dict[int, float]:
    """Per-lag Granger F-test p-value for `cause` → `effect`.

    Statsmodels regresses `effect[t]` on its own lags plus lags of
    `cause`, then tests the joint hypothesis that the `cause` lag
    coefficients are zero. p < 0.05 means past `cause` Granger-causes
    `effect` at that lag.
    """
    if cause.shape != effect.shape:
        raise ValueError("cause and effect must have the same shape")
    data = np.column_stack([effect, cause])  # statsmodels wants (Y, X) order
    results = grangercausalitytests(data, max_lag, verbose=False)
    out: dict[int, float] = {}
    for lag, payload_obj in results.items():
        payload = cast(tuple[dict[str, Any], Any], payload_obj)
        stats_dict = payload[0]
        # Use the F-test p-value (the most common convention).
        out[int(lag)] = float(stats_dict["ssr_ftest"][1])
    return out
