# penumbra-analytics

Real statistical analysis on the simulation tick stream.

## Concept taught — 12 modules, one practice per

| Module | Technique |
|---|---|
| `descriptive` | summary stats with robust alternatives (trimmed mean, IQR) and bootstrap CIs |
| `inferential` | non-parametric tests: Mann-Whitney U, permutation, χ²; Cliff's δ effect size |
| `econometrics` | OLS with Newey-West HAC SEs, VAR(p) via AIC, Granger causality F-test |
| `monte_carlo` | scrambled Sobol QMC, quasi-MC integration with batch-means SE, empirical VaR/CVaR, bootstrap mean CI |
| `linalg` | symmetric-normalised graph Laplacian, spectral embedding via shift-invert eigsh, Ng-Jordan-Weiss spectral clustering, algebraic connectivity |
| `clustering` | HDBSCAN density-based clustering with noise labels |
| `time_series` | ARIMA one-step forecast, 1-D Kalman filter, PELT-style mean-changepoint detection |
| `bayesian` | NumPyro SVI for beta-binomial posteriors and Bayesian linear regression |
| `survival` | Kaplan-Meier curve with CIs, Cox proportional-hazards regression |
| `topology` | persistent homology via ripser (Vietoris-Rips), persistence lifetimes, total persistence |
| `transport` | Sinkhorn-regularised optimal transport plans, exact 1-D Wasserstein via CDFs |
| `causal` | propensity-score estimation (with clipping), IPW ATE, AIPW doubly-robust ATE |
| `dashboard_pipeline` | streaming orchestrator: rolling buffers + per-consumer cadences, snapshot polling for the frontend |

Each module is a small, self-contained file with a `Concept taught:`
line in its module docstring — the launching point for the dedicated
`@learner` conversation about that technique.

## Micro-experiments

1. **Detect a structural break in a time series**:
   ```python
   import numpy as np
   from penumbra_analytics.time_series import detect_mean_changepoints
   rng = np.random.default_rng(7)
   series = np.concatenate([rng.normal(0, 0.5, 100), rng.normal(3, 0.5, 100)])
   detect_mean_changepoints(series, penalty=5.0)  # → near [100]
   ```
2. **Confirm causal inference beats naïve regression**:
   ```python
   # See packages/analytics/tests/test_causal.py — the test
   # test_aipw_more_precise_than_naive_difference_in_means is the demo.
   ```
3. **Watch the dashboard pipeline live**: hit `/dashboard` while the
   backend is running — values fill in as each consumer's rolling
   window crosses its threshold (descriptive @ 30 obs, ARIMA @ 50,
   topology @ 10, …).

## Public API

```python
from penumbra_analytics import (
    descriptive, inferential, econometrics, monte_carlo,
    linalg, clustering, time_series, bayesian, survival,
    topology, transport, causal,
)
from penumbra_analytics.dashboard_pipeline import DashboardPipeline, DashboardSnapshot
```

## Deferred

- `topics.py` (BERTopic) — agent utterances don't exist yet; module
  is left as a docs-stub. ~500 MB of HuggingFace deps would arrive
  with it.
