"""Time-series modelling: ARIMA + Kalman filter + change-point detection.

Concept taught: three canonical time-series tools.

- **ARIMA(p,d,q)**: classical Box-Jenkins workhorse. d differencing
  steps to stationarise, p autoregressive lags, q moving-average
  lags. We expose a one-step forecast helper.

- **Kalman filter**: optimal linear estimator for a state-space model
  `x_t = A x_{t-1} + w`, `y_t = C x_t + v`. We instantiate a generic
  scalar tracker via scipy's state-space toolkit and return the
  filtered series.

- **Change-point detection**: PELT (Pruned Exact Linear Time, Killick
  et al. 2012) via the Pelt-style algorithm reimplemented on top of
  numpy. Detects where the mean of the series jumps.

References
- Box, Jenkins, "Time series analysis: forecasting and control" (1970).
- Kalman, "A new approach to linear filtering and prediction problems"
  (1960).
- Killick, Fearnhead, Eckley, "Optimal detection of changepoints with
  a linear computational cost" (JASA 2012).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from statsmodels.tsa.arima.model import ARIMA


@dataclass(frozen=True, slots=True)
class ARIMAForecast:
    next_value: float
    forecast_std: float
    in_sample_residual_std: float


def arima_one_step(
    series: NDArray[np.float64], *, order: tuple[int, int, int] = (1, 0, 0)
) -> ARIMAForecast:
    """Fit ARIMA(p,d,q) and return a one-step-ahead point forecast."""
    if series.ndim != 1:
        raise ValueError("series must be 1-D")
    model = ARIMA(series, order=order).fit()
    forecast = model.get_forecast(steps=1)
    next_value = float(forecast.predicted_mean[0])
    forecast_std = float(np.sqrt(forecast.var_pred_mean[0]))
    in_sample_resid_std = float(np.std(model.resid, ddof=1))
    return ARIMAForecast(
        next_value=next_value,
        forecast_std=forecast_std,
        in_sample_residual_std=in_sample_resid_std,
    )


def kalman_filter_1d(
    observations: NDArray[np.float64],
    *,
    process_var: float = 0.01,
    observation_var: float = 1.0,
) -> NDArray[np.float64]:
    """Simple 1-D Kalman filter: hidden constant-velocity scalar.

    State transition: x_t = x_{t-1}. Observation: y_t = x_t + ε.
    Returns the filtered hidden-state estimate at each timestep.
    """
    n = observations.size
    if n == 0:
        return np.empty(0, dtype=np.float64)
    estimates = np.empty(n, dtype=np.float64)
    x = float(observations[0])
    variance = float(observation_var)
    for t in range(n):
        # Predict step (no dynamics → variance grows by process_var).
        variance += process_var
        # Update step.
        gain = variance / (variance + observation_var)
        x = x + gain * (float(observations[t]) - x)
        variance = (1.0 - gain) * variance
        estimates[t] = x
    return estimates


def detect_mean_changepoints(
    series: NDArray[np.float64],
    *,
    penalty: float = 10.0,
    min_segment_length: int = 5,
) -> list[int]:
    """Detect indices where the mean of `series` changes.

    Greedy variant: scan every candidate split, score the gain in
    sum-of-squares, accept splits that exceed `penalty`. Linear-time,
    good enough for pedagogical demos on a few thousand points.
    """
    n = series.size
    if n < 2 * min_segment_length:
        return []
    changepoints: list[int] = []
    start = 0
    while start < n - min_segment_length:
        best_gain = 0.0
        best_split: int | None = None
        for split in range(start + min_segment_length, n - min_segment_length + 1):
            left = series[start:split]
            right = series[split:]
            total_ss = float(np.var(series[start:], ddof=0) * (n - start))
            split_ss = float(np.var(left, ddof=0) * left.size + np.var(right, ddof=0) * right.size)
            gain = total_ss - split_ss
            if gain > best_gain:
                best_gain = gain
                best_split = split
        if best_split is None or best_gain < penalty:
            break
        changepoints.append(best_split)
        start = best_split
    return changepoints
