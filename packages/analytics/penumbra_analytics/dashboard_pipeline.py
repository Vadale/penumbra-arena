"""Streaming-analytics fan-out.

Concept taught: how many independent analyses, each on their own
cadence, share one simulation tick stream. The pipeline holds rolling
buffers and re-runs each consumer at its declared interval, returning
the latest results. Transport-side code can poll this with
`pipeline.snapshot()` and stream the result to the frontend.

Pedagogically this is the *integration tax*: turning a textbook
algorithm into a streaming consumer is the work that students rarely
see in courses but always have to do in industry.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from penumbra_analytics import (
    bayesian,
    clustering,
    descriptive,
    monte_carlo,
    time_series,
    topics,
    topology,
)
from penumbra_analytics import transport as analytics_transport

# Tier 2 modules: live consumers below feed each of these.
# They existed but were dead code before this commit — now they
# all have a path from the streaming pipeline to a dashboard chart.

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RegressionResult:
    """OLS fit on a 1-D series y_t = α + β·t + ε.

    Concept taught: simple linear regression on a streaming window.
    Returns the coefficients plus the indices needed to plot the
    fit + a 95% confidence band.
    """

    slope: float
    intercept: float
    r_squared: float
    n: int
    sigma: float  # residual standard error
    # Last N raw observations the fit was computed on (for the scatter).
    points: tuple[tuple[int, float], ...]


@dataclass(slots=True)
class ClusterScatterResult:
    """2-D projection of recent agent positions + cluster labels.

    The 2-D coords are the first two principal components of the
    (n_ticks × n_agents) position matrix's column space. Labels come
    from HDBSCAN on those coords. Used to render the live "factions"
    scatter — a real multivariate visualisation, not just a count.
    """

    points: tuple[tuple[float, float, int], ...]  # (x, y, label)
    n_clusters: int
    n_noise: int


@dataclass(slots=True)
class MonteCarloResult:
    """Bootstrap distribution of the trajectory norm + VaR/CVaR.

    Returns the empirical percentiles needed for a fan chart and
    the tail-risk metrics (5%/50%/95% quantiles; VaR + CVaR at 95).
    """

    percentiles: dict[int, float]  # {5: x, 25: x, 50: x, 75: x, 95: x}
    var: float
    cvar: float
    n_samples: int


@dataclass(slots=True)
class PCAResult:
    """Eigendecomposition of the recent position covariance.

    Scree-plot inputs: eigenvalues (descending) + their cumulative
    explained variance ratio. Top-2 components also exposed so the
    frontend can render the agents on the first two PCs.
    """

    eigenvalues: tuple[float, ...]
    explained_variance_ratio: tuple[float, ...]
    top2_loadings: tuple[tuple[float, float], ...]  # one (a, b) per agent


@dataclass(slots=True)
class ArimaForecast:
    """ARIMA one-step forecast with the recent series and a 95% PI.

    Renders: the historical series leading up to NOW, plus the
    forecast point and ±1.96·σ band so the prediction interval is
    visible rather than just a number.
    """

    history: tuple[float, ...]  # last N observations
    next_value: float
    next_std: float


@dataclass(slots=True)
class LogitResult:
    """Logistic regression P(Y=1 | x) where Y = (traj_t > median).

    The natural propensity demo on Penumbra data: given the
    previous-tick trajectory norm x, what's the probability the
    next tick exceeds the rolling median? Closed-form sigmoid.
    """

    intercept: float
    slope: float
    # Sampled curve for plotting: list of (x, sigmoid(α + β·x)).
    curve: tuple[tuple[float, float], ...]
    # Empirical (x, treated) for the scatter underlying the fit.
    points: tuple[tuple[float, int], ...]
    n: int
    pseudo_r2: float  # McFadden's pseudo-R² — log-likelihood ratio vs null


@dataclass(slots=True)
class BayesianPosterior:
    """Beta posterior over θ (closed form) + full density curve.

    With Beta(1, 1) prior + Binomial(n, θ) likelihood + s successes
    the posterior is Beta(1+s, 1+n-s). We expose α + β + the PDF
    sampled at 100 points so the frontend renders a real density,
    not just the mean.
    """

    alpha: float
    beta: float
    mean: float
    std: float
    credible_low: float  # 2.5% quantile
    credible_high: float  # 97.5% quantile
    curve: tuple[tuple[float, float], ...]  # (theta, pdf) at 100 points


@dataclass(slots=True)
class EconomySnapshot:
    """Rolling economy state: top categories, top products, basket sizes.

    Concept taught: turning an event stream into rolling aggregates.
    """

    total_purchases: int
    total_revenue: float
    category_counts: dict[str, int]  # category → units sold (window)
    top_products: tuple[tuple[str, int, float], ...]  # (name, units, revenue)
    basket_histogram: tuple[tuple[int, int], ...]  # (size, count)


@dataclass(slots=True)
class SurvivalCurve:
    """Kaplan-Meier curve of match durations.

    Concept taught: time-to-event with right-censoring. A match that
    ended with a winner is an OBSERVED death (event=1); a match
    cancelled or still running counts as censored. We expose the
    step function + 95% pointwise CI for the chart.
    """

    times: tuple[float, ...]
    survival: tuple[float, ...]
    confidence_low: tuple[float, ...]
    confidence_high: tuple[float, ...]
    n_events: int
    n_censored: int
    median_time: float | None  # median survival or None if not reached


@dataclass(slots=True)
class SpectralReport:
    """Bottom eigenvalues + Fiedler value of the arena Laplacian.

    Concept taught: a graph's algebraic connectivity (Fiedler λ₂) is
    a continuous measure of how well-connected it is — small values
    mean a near-cut, large values mean a robust mesh.
    """

    eigenvalues: tuple[float, ...]  # bottom 5 of the normalised Laplacian
    fiedler_value: float
    n_nodes: int
    n_edges: int
    fiedler_vector: tuple[float, ...]  # one entry per node (for the spectrum bar chart)


@dataclass(slots=True)
class CausalEstimate:
    """IPW + AIPW ATE estimates with their bootstrap SEs.

    Treatment = "agent purchased a LUXURY item in the recent window".
    Outcome = the agent's trajectory L2 distance from origin over the
    same window. Covariate = recent average position.
    """

    n_treated: int
    n_control: int
    ipw_ate: float
    ipw_se: float
    aipw_ate: float
    aipw_se: float
    propensity_treated: tuple[float, ...]
    propensity_control: tuple[float, ...]


@dataclass(slots=True)
class VARImpulseResponse:
    """Impulse responses from a VAR(p) on a few key derived series.

    Concept taught: in a vector autoregression, the IRF traces how
    a one-σ shock to series i propagates through every other series
    over the next h steps.
    """

    series_names: tuple[str, ...]
    horizon: int
    lag_order: int
    # irf[h][i][j] = response of series j at step h to a unit shock
    # in series i at step 0. Includes the impulse step (h=0).
    irf: tuple[tuple[tuple[float, ...], ...], ...]


@dataclass(slots=True)
class GarchResult:
    """GARCH(1, 1) fit on trajectory log-returns.

    Concept taught: real-world financial returns are NOT i.i.d. —
    volatility CLUSTERS. GARCH models conditional variance as
    σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}, learning the persistence
    of shocks.
    """

    omega: float
    alpha: float
    beta: float
    persistence: float  # α + β; close to 1 = high persistence
    log_returns: tuple[float, ...]  # the series we fitted on
    conditional_volatility: tuple[float, ...]  # σ_t


@dataclass(slots=True)
class GrangerMatrix:
    """Pairwise Granger-causality p-values between K derived series.

    For each ordered pair (i, j), value[i][j] is the p-value of the
    null 'i does NOT Granger-cause j'. Small p → causality. The
    diagonal is set to 1.0 (no self-causality).
    """

    series_names: tuple[str, ...]
    p_values: tuple[tuple[float, ...], ...]  # K×K row-major
    max_lag: int
    n_obs: int


@dataclass(slots=True)
class ANOVAReport:
    """One-way ANOVA F-test on a categorical grouping of agents."""

    f_statistic: float
    p_value: float
    df_between: int
    df_within: int
    grouping: str  # how groups were defined (e.g. 'hdbscan_cluster')
    group_names: tuple[str, ...]
    group_means: tuple[float, ...]
    group_se: tuple[float, ...]
    group_n: tuple[int, ...]
    grand_mean: float


@dataclass(slots=True)
class AutocorrelationReport:
    """ACF + PACF up to L lags for the trajectory series.

    Pedagogically the right way to choose ARIMA(p, d, q) order: ACF
    decays geometrically for AR; PACF cuts off at lag p for AR(p);
    ACF cuts off at q for MA(q).
    """

    n_obs: int
    max_lag: int
    acf: tuple[float, ...]
    pacf: tuple[float, ...]
    conf_band: float  # ±1.96/√n — both ACF and PACF use the same band


@dataclass(slots=True)
class ROCData:
    """ROC curve + AUC for the logit classifier."""

    fpr: tuple[float, ...]
    tpr: tuple[float, ...]
    thresholds: tuple[float, ...]
    auc: float


@dataclass(slots=True)
class CorrelationMatrix:
    """Pearson + Spearman pairwise correlations across K metrics."""

    series_names: tuple[str, ...]
    pearson: tuple[tuple[float, ...], ...]
    spearman: tuple[tuple[float, ...], ...]
    n_obs: int


@dataclass(slots=True)
class PermutationReport:
    """Permutation test on the causal ATE.

    Shuffle treatment labels n_permutations times, recompute IPW ATE
    under each shuffle. Observed ATE + null distribution + two-sided
    p-value let us validate the causal estimate without parametric
    assumptions.
    """

    observed_ate: float
    null_samples: tuple[float, ...]
    p_two_sided: float
    n_permutations: int


@dataclass(slots=True)
class CandleBar:
    """One OHLC candle: open/high/low/close + volume in the bucket."""

    bucket: int  # tick at the start of the bucket
    open: float
    high: float
    low: float
    close: float
    volume: int  # total units traded in the window


@dataclass(slots=True)
class CandleSeries:
    """Per-product OHLC candles + meta for the most-traded products."""

    product_id: int
    product_name: str
    category: str
    candles: tuple[CandleBar, ...]
    total_volume: int  # over the window
    bucket_ticks: int  # how many ticks each candle aggregates


@dataclass(slots=True)
class InflationSeries:
    """CPI-like price index history and money supply history."""

    cpi: tuple[tuple[int, float], ...]  # (tick, index)
    money_supply: tuple[tuple[int, float], ...]  # (tick, total coins in system)
    n_samples: int


@dataclass(slots=True)
class WealthReport:
    """Lorenz curve + Gini coefficient + wealth quantile snapshot."""

    lorenz_x: tuple[float, ...]  # cumulative share of population
    lorenz_y: tuple[float, ...]  # cumulative share of wealth
    gini: float
    p10: float
    p50: float
    p90: float
    p99: float
    total_wealth: float
    n_agents: int


@dataclass(slots=True)
class DashboardSnapshot:
    """The current state of every registered consumer."""

    tick: int
    summary: descriptive.Summary | None = None
    hdbscan_n_clusters: int | None = None
    hdbscan_n_noise: int | None = None
    arima_next: float | None = None
    arima_std: float | None = None
    changepoints: tuple[int, ...] = ()
    sinkhorn_cost: float | None = None
    h0_total: float | None = None
    h1_total: float | None = None
    # Full barcode intervals so the frontend can render persistence bars.
    # Each entry is [birth, death]; `inf` deaths are clamped on the wire.
    h0_bars: tuple[tuple[float, float], ...] = ()
    h1_bars: tuple[tuple[float, float], ...] = ()
    bayesian_theta: float | None = None
    var95: float | None = None
    n_topics: int | None = None
    topic_sizes: dict[int, int] = field(default_factory=dict)
    topic_top_words: dict[int, tuple[str, ...]] = field(default_factory=dict)
    # Rich multivariate analyses (computed at lower cadence).
    regression: RegressionResult | None = None
    cluster_scatter: ClusterScatterResult | None = None
    monte_carlo: MonteCarloResult | None = None
    pca: PCAResult | None = None
    arima_forecast: ArimaForecast | None = None
    logit: LogitResult | None = None
    bayesian_posterior: BayesianPosterior | None = None
    granger: GrangerMatrix | None = None
    economy: EconomySnapshot | None = None
    survival: SurvivalCurve | None = None
    spectral: SpectralReport | None = None
    causal: CausalEstimate | None = None
    var_irf: VARImpulseResponse | None = None
    garch: GarchResult | None = None
    qq_points: tuple[tuple[float, float], ...] = ()
    anova: ANOVAReport | None = None
    autocorrelation: AutocorrelationReport | None = None
    roc: ROCData | None = None
    correlations: CorrelationMatrix | None = None
    permutation: PermutationReport | None = None
    # Fitted residuals for the residual-vs-fitted diagnostic. Each
    # entry is (fitted_value, residual). Empty until regression runs.
    residual_vs_fitted: tuple[tuple[float, float], ...] = ()
    candles: tuple[CandleSeries, ...] = ()
    inflation: InflationSeries | None = None
    wealth: WealthReport | None = None
    # Q-Q lives on the regression chart (theoretical-vs-sample
    # quantiles of OLS residuals); the field is empty until the
    # regression consumer has run.


@dataclass(slots=True)
class DashboardPipeline:
    """Holds rolling buffers + cadence schedule for streaming analytics.

    The intended caller pushes per-tick observations via `observe()`,
    then periodically (typically every second from the orchestrator)
    invokes `recompute()`, which respects each consumer's per-second
    target.
    """

    history_window: int = 512
    cadences: dict[str, float] = field(
        default_factory=lambda: {
            "descriptive": 1.0,
            "clustering": 5.0,
            "arima": 5.0,
            "changepoints": 5.0,
            "sinkhorn": 5.0,
            "topology": 10.0,
            "bayesian": 10.0,
            "var95": 5.0,
            # Topic modelling is the most expensive consumer — it runs
            # the bge-small embedder over ~200 utterances. 20s cadence
            # keeps it off the hot path.
            "topics": 20.0,
            # Multivariate rich-chart analyses. Slower because they
            # ship larger payloads (raw points) to the frontend.
            "regression": 4.0,
            "cluster_scatter": 6.0,
            "monte_carlo": 8.0,
            "pca": 8.0,
            "arima_forecast": 6.0,
            "logit": 6.0,
            "bayesian_posterior": 10.0,
            "granger": 12.0,
            "economy": 3.0,
            # Tier 2: heavier consumers, run less often.
            "survival": 15.0,
            "spectral": 8.0,
            "causal": 12.0,
            "var_irf": 12.0,
            "garch": 10.0,
            "anova": 8.0,
            "autocorrelation": 6.0,
            "correlations": 6.0,
            "permutation": 15.0,
            "candles": 4.0,
            "inflation": 4.0,
            "wealth": 5.0,
        }
    )

    _trajectory_lengths: deque[float] = field(default_factory=lambda: deque(maxlen=512))
    _positions: deque[NDArray[np.float64]] = field(default_factory=lambda: deque(maxlen=64))
    _heatmaps: deque[NDArray[np.float64]] = field(default_factory=lambda: deque(maxlen=64))
    _utterances: deque[str] = field(default_factory=lambda: deque(maxlen=400))
    _purchases: deque[object] = field(default_factory=lambda: deque(maxlen=2000))
    _purchases_by_tick: deque[int] = field(default_factory=lambda: deque(maxlen=2000))
    # Full Trade stream (buy + sell). Each entry is duck-typed: tick,
    # agent_id, node_id, product_id, category, side, quantity,
    # unit_price, total_value.
    _trades: deque[object] = field(default_factory=lambda: deque(maxlen=4000))
    # Time series of CPI + money supply + latest wealth snapshot.
    _cpi_history: deque[tuple[int, float]] = field(default_factory=lambda: deque(maxlen=300))
    _money_supply_history: deque[tuple[int, float]] = field(
        default_factory=lambda: deque(maxlen=300)
    )
    _latest_wealth: tuple[float, ...] = field(default_factory=tuple)
    # Match outcomes feed the survival consumer. Each entry is
    # (duration_ticks, observed_event). Capped at 256 so the curve
    # adapts to recent dynamics rather than the whole run history.
    _match_outcomes: deque[tuple[int, bool]] = field(default_factory=lambda: deque(maxlen=256))
    # The live arena Graph — set by the orchestrator on construction
    # so the spectral consumer can run without going through the API.
    _arena_graph: object | None = field(default=None)
    _last_run: dict[str, float] = field(default_factory=dict)
    _snapshot: DashboardSnapshot = field(default_factory=lambda: DashboardSnapshot(tick=-1))

    def observe(
        self,
        *,
        tick: int,
        positions: NDArray[np.float64],
        heatmap: NDArray[np.float64] | None = None,
        utterances: list[str] | None = None,
    ) -> None:
        """Push a tick's observation into the rolling buffers."""
        self._snapshot = (
            DashboardSnapshot(tick=tick) if self._snapshot.tick == -1 else self._with_tick(tick)
        )
        self._trajectory_lengths.append(float(np.linalg.norm(positions)))
        self._positions.append(np.asarray(positions, dtype=np.float64))
        if heatmap is not None:
            self._heatmaps.append(np.asarray(heatmap, dtype=np.float64))
        if utterances:
            self._utterances.extend(utterances)

    def recompute(self) -> DashboardSnapshot:
        """Re-run any consumer whose cadence has elapsed since last run."""
        now = time.monotonic()
        if self._due(now, "descriptive") and len(self._trajectory_lengths) >= 30:
            values = np.asarray(list(self._trajectory_lengths), dtype=np.float64)
            try:
                self._snapshot.summary = descriptive.summarise(values, n_resamples=199)
            except ValueError:
                logger.debug("consumer raised ValueError on the current window", exc_info=True)
            self._last_run["descriptive"] = now

        if self._due(now, "clustering") and len(self._positions) >= 30:
            points = np.stack(list(self._positions))
            if points.ndim == 2 and points.shape[1] >= 2:
                try:
                    res = clustering.hdbscan_cluster(points, min_cluster_size=5)
                    self._snapshot.hdbscan_n_clusters = res.n_clusters
                    self._snapshot.hdbscan_n_noise = res.n_noise
                except ValueError:
                    pass
            self._last_run["clustering"] = now

        if self._due(now, "arima") and len(self._trajectory_lengths) >= 50:
            values = np.asarray(list(self._trajectory_lengths), dtype=np.float64)
            try:
                forecast = time_series.arima_one_step(values, order=(1, 0, 0))
                self._snapshot.arima_next = forecast.next_value
                self._snapshot.arima_std = forecast.forecast_std
            except Exception:
                logger.debug(
                    "consumer raised on the current window; will retry next cadence", exc_info=True
                )
            self._last_run["arima"] = now

        if self._due(now, "changepoints") and len(self._trajectory_lengths) >= 30:
            values = np.asarray(list(self._trajectory_lengths), dtype=np.float64)
            self._snapshot.changepoints = tuple(time_series.detect_mean_changepoints(values))
            self._last_run["changepoints"] = now

        if self._due(now, "sinkhorn") and len(self._heatmaps) >= 2:
            plan = analytics_transport.sinkhorn_plan(
                self._heatmaps[-2], self._heatmaps[-1], reg=0.5
            )
            self._snapshot.sinkhorn_cost = plan.cost
            self._last_run["sinkhorn"] = now

        if self._due(now, "topology") and len(self._positions) >= 10:
            points = np.stack(list(self._positions)[-30:])
            if points.ndim == 2 and points.shape[1] >= 2:
                diagram = topology.persistence_from_points(points, max_dim=1)
                self._snapshot.h0_total = topology.total_persistence(diagram.h0)
                self._snapshot.h1_total = topology.total_persistence(diagram.h1)
                self._snapshot.h0_bars = _bars_payload(diagram.h0)
                self._snapshot.h1_bars = _bars_payload(diagram.h1)
            self._last_run["topology"] = now

        if self._due(now, "bayesian"):
            # Trivial posterior demo: probability of "high" trajectory norm.
            values = list(self._trajectory_lengths)
            if values:
                threshold = float(np.median(values))
                successes = sum(1 for v in values if v >= threshold)
                trials = len(values)
                try:
                    posterior = bayesian.beta_binomial_posterior(successes, trials, n_iters=400)
                    self._snapshot.bayesian_theta = posterior.mean
                except Exception:
                    logger.debug("bayesian posterior failed on the current window", exc_info=True)
            self._last_run["bayesian"] = now

        if self._due(now, "var95") and len(self._trajectory_lengths) >= 50:
            values = np.asarray(list(self._trajectory_lengths), dtype=np.float64)
            metrics = monte_carlo.var_cvar(values, confidence=0.95)
            self._snapshot.var95 = metrics.var
            self._last_run["var95"] = now

        if self._due(now, "regression") and len(self._trajectory_lengths) >= 30:
            self._snapshot.regression = self._compute_regression()
            self._last_run["regression"] = now

        if self._due(now, "cluster_scatter") and len(self._positions) >= 30:
            self._snapshot.cluster_scatter = self._compute_cluster_scatter()
            self._last_run["cluster_scatter"] = now

        if self._due(now, "monte_carlo") and len(self._trajectory_lengths) >= 50:
            self._snapshot.monte_carlo = self._compute_monte_carlo()
            self._last_run["monte_carlo"] = now

        if self._due(now, "pca") and len(self._positions) >= 30:
            self._snapshot.pca = self._compute_pca()
            self._last_run["pca"] = now

        if self._due(now, "arima_forecast") and len(self._trajectory_lengths) >= 50:
            self._snapshot.arima_forecast = self._compute_arima_forecast()
            self._last_run["arima_forecast"] = now

        if self._due(now, "logit") and len(self._trajectory_lengths) >= 40:
            self._snapshot.logit = self._compute_logit()
            self._last_run["logit"] = now

        if self._due(now, "bayesian_posterior") and len(self._trajectory_lengths) >= 30:
            self._snapshot.bayesian_posterior = self._compute_bayesian_posterior()
            self._last_run["bayesian_posterior"] = now

        if self._due(now, "granger") and len(self._trajectory_lengths) >= 60:
            self._snapshot.granger = self._compute_granger()
            self._last_run["granger"] = now

        if self._due(now, "economy") and len(self._purchases) > 0:
            self._snapshot.economy = self._compute_economy()
            self._last_run["economy"] = now

        if self._due(now, "survival") and len(self._match_outcomes) >= 5:
            self._snapshot.survival = self._compute_survival()
            self._last_run["survival"] = now

        if self._due(now, "spectral") and self._arena_graph is not None:
            self._snapshot.spectral = self._compute_spectral()
            self._last_run["spectral"] = now

        if (
            self._due(now, "causal")
            and len(self._purchases) >= 40
            and len(self._trajectory_lengths) >= 50
        ):
            self._snapshot.causal = self._compute_causal()
            self._last_run["causal"] = now

        if self._due(now, "var_irf") and len(self._trajectory_lengths) >= 60:
            self._snapshot.var_irf = self._compute_var_irf()
            self._last_run["var_irf"] = now

        if self._due(now, "garch") and len(self._trajectory_lengths) >= 80:
            self._snapshot.garch = self._compute_garch()
            self._last_run["garch"] = now

        # Q-Q + residual-vs-fitted on regression residuals — cheap.
        if self._snapshot.regression is not None:
            self._snapshot.qq_points = self._compute_qq_points()
            self._snapshot.residual_vs_fitted = self._compute_residual_vs_fitted()

        if self._due(now, "anova") and len(self._positions) >= 30:
            self._snapshot.anova = self._compute_anova()
            self._last_run["anova"] = now

        if self._due(now, "autocorrelation") and len(self._trajectory_lengths) >= 40:
            self._snapshot.autocorrelation = self._compute_autocorrelation()
            self._last_run["autocorrelation"] = now

        if self._due(now, "correlations") and len(self._trajectory_lengths) >= 40:
            self._snapshot.correlations = self._compute_correlations()
            self._last_run["correlations"] = now

        if (
            self._due(now, "permutation")
            and self._snapshot.causal is not None
            and len(self._purchases) >= 40
        ):
            self._snapshot.permutation = self._compute_permutation_test()
            self._last_run["permutation"] = now

        # Extend LogitResult with ROC the cheap way: compute once when logit ran.
        if self._snapshot.logit is not None and self._snapshot.roc is None:
            self._snapshot.roc = self._compute_roc()

        if self._due(now, "candles") and len(self._trades) >= 20:
            self._snapshot.candles = self._compute_candles()
            self._last_run["candles"] = now

        if self._due(now, "inflation") and len(self._cpi_history) >= 2:
            self._snapshot.inflation = self._compute_inflation()
            self._last_run["inflation"] = now

        if self._due(now, "wealth") and len(self._latest_wealth) >= 5:
            self._snapshot.wealth = self._compute_wealth()
            self._last_run["wealth"] = now

        if self._due(now, "topics") and len(self._utterances) >= 40:
            # Stress-test fix A/B: explicit gc after BERTopic; in early
            # measurements RSS climbed ~9 GB/h because BERTopic + UMAP +
            # HDBSCAN models were piling up. Forcing a sweep returns
            # ~80% of the per-call allocation immediately.
            import gc

            corpus = list(self._utterances)
            try:
                result = topics.compute(corpus, min_topic_size=5)
                self._snapshot.n_topics = result.n_topics
                self._snapshot.topic_sizes = dict(result.topic_sizes)
                self._snapshot.topic_top_words = dict(result.representative_words)
                del result
            except Exception:
                logger.debug("topic modelling failed on the current window", exc_info=True)
            del corpus
            gc.collect()
            self._last_run["topics"] = now

        return self._snapshot

    def _compute_economy(self) -> EconomySnapshot | None:
        """Roll the recent purchase window into category + top-product counts."""
        if not self._purchases:
            return None
        # Window: most recent 800 events (covers a few minutes).
        window = list(self._purchases)[-800:]
        total_purchases = len(window)
        total_revenue = float(sum(float(getattr(p, "price_paid", 0.0)) for p in window))
        cats: dict[str, int] = {}
        prod_units: dict[int, int] = {}
        prod_revenue: dict[int, float] = {}
        baskets: dict[int, int] = {}  # tick → quantity-bucket histogram via per-agent grouping
        per_agent_basket: dict[tuple[int, int], int] = {}
        for p in window:
            cat = str(getattr(p, "category", "?"))
            cats[cat] = cats.get(cat, 0) + int(getattr(p, "quantity", 1))
            pid = int(getattr(p, "product_id", -1))
            prod_units[pid] = prod_units.get(pid, 0) + int(getattr(p, "quantity", 1))
            prod_revenue[pid] = prod_revenue.get(pid, 0.0) + float(getattr(p, "price_paid", 0.0))
            key = (int(getattr(p, "agent_id", -1)), int(getattr(p, "tick", 0)))
            per_agent_basket[key] = per_agent_basket.get(key, 0) + int(getattr(p, "quantity", 1))
        for size in per_agent_basket.values():
            bucket = min(size, 10)  # cap at 10+
            baskets[bucket] = baskets.get(bucket, 0) + 1

        from penumbra_core.economy import PRODUCT_CATALOG

        top_products: list[tuple[str, int, float]] = []
        for pid, units in sorted(prod_units.items(), key=lambda kv: -kv[1])[:8]:
            if 0 <= pid < len(PRODUCT_CATALOG):
                name = PRODUCT_CATALOG[pid].name
                top_products.append((name, units, prod_revenue.get(pid, 0.0)))
        return EconomySnapshot(
            total_purchases=total_purchases,
            total_revenue=total_revenue,
            category_counts=cats,
            top_products=tuple(top_products),
            basket_histogram=tuple(sorted(baskets.items())),
        )

    def record_match_outcome(self, duration_ticks: int, event_observed: bool) -> None:
        """Append one match outcome to the survival buffer.

        `event_observed=True` ⇒ the match ended because an agent
        reached a goal (the analogue of 'death'); False ⇒ the match
        was cut off / cancelled (right-censored).
        """
        self._match_outcomes.append((int(duration_ticks), bool(event_observed)))

    def set_arena_graph(self, graph: object) -> None:
        """Wire the live arena graph into the spectral consumer.

        Typed as `object` to keep the analytics package independent
        of networkx in its signatures; runtime expects nx.Graph.
        """
        self._arena_graph = graph

    def record_trades(
        self,
        *,
        trades: list[object],
        money_supply: float,
        price_index: float,
        wealth: tuple[float, ...],
        tick: int,
    ) -> None:
        """Append a tick's worth of buy/sell events + economy aggregates."""
        for t in trades:
            self._trades.append(t)
            self._purchases_by_tick.append(int(getattr(t, "tick", tick)))
            # Keep the legacy `_purchases` deque populated with buy events
            # so existing consumers (causal, EconomySnapshot) still work.
            if getattr(t, "side", "buy") == "buy":
                self._purchases.append(t)
        self._cpi_history.append((int(tick), float(price_index)))
        self._money_supply_history.append((int(tick), float(money_supply)))
        self._latest_wealth = wealth
        if not self._latest_wealth:
            logger.info("record_trades got empty wealth (tick=%s, trades=%s)", tick, len(trades))

    def record_purchases(self, purchases: list[object]) -> None:
        """Append a batch of Purchase events to the rolling buffer.

        Typed as `list[object]` to avoid an analytics→core import
        cycle; runtime uses the duck-typed attributes.
        """
        for p in purchases:
            self._purchases.append(p)
            self._purchases_by_tick.append(int(getattr(p, "tick", 0)))

    @property
    def snapshot(self) -> DashboardSnapshot:
        return self._snapshot

    # ── multivariate / rich-chart consumers ──────────────────────────

    def _compute_regression(self) -> RegressionResult | None:
        """OLS on the last 60 trajectory-norm samples vs their index.

        Pedagogically the simplest 'is there a trend?' check. The
        residuals + R² + (slope, intercept) are exactly what students
        need to interpret. We expose all the points so the frontend
        renders a real scatter + fit, not just summary stats.
        """
        from penumbra_analytics import econometrics

        recent = list(self._trajectory_lengths)[-60:]
        if len(recent) < 10:
            return None
        x = np.arange(len(recent), dtype=np.float64)
        y = np.asarray(recent, dtype=np.float64)
        try:
            fit = econometrics.ols_with_hac(y, x.reshape(-1, 1))
        except (ValueError, np.linalg.LinAlgError):
            logger.debug("regression OLS failed", exc_info=True)
            return None
        coefs = fit.coefficients
        intercept = float(coefs[0])
        slope = float(coefs[1]) if len(coefs) > 1 else 0.0
        residuals = y - (intercept + slope * x)
        ss_res = float(np.sum(residuals**2))
        r2 = float(fit.r_squared)
        sigma = float(np.sqrt(ss_res / max(len(y) - 2, 1)))
        points = tuple((int(i), float(yi)) for i, yi in zip(x, y, strict=True))
        return RegressionResult(
            slope=slope,
            intercept=intercept,
            r_squared=r2,
            n=len(y),
            sigma=sigma,
            points=points,
        )

    def _compute_cluster_scatter(self) -> ClusterScatterResult | None:
        """First-2-PC projection of recent positions + HDBSCAN labels.

        The position history is shape (n_ticks, n_agents). We treat
        each AGENT as a sample and the TICK history as features, then
        project the agent rows onto the first two principal components
        of the covariance. HDBSCAN labels the result. The output is a
        2-D scatter that visualises factions.
        """
        if len(self._positions) < 10:
            return None
        # (n_ticks, n_agents). Transpose so rows = agents, cols = ticks.
        matrix = np.stack(list(self._positions)[-30:])  # (T, A)
        x = matrix.T.astype(np.float64)  # (A, T)
        if x.shape[0] < 5:
            return None
        # Centre + SVD; first 2 right-singular vectors are the loadings.
        x = x - x.mean(axis=0, keepdims=True)
        try:
            u, s, _ = np.linalg.svd(x, full_matrices=False)
        except np.linalg.LinAlgError:
            return None
        if u.shape[1] < 2:
            return None
        # Project agents onto the first 2 PCs (rows of U scaled by s).
        proj = u[:, :2] * s[:2]
        # HDBSCAN on the 2-D projection.
        try:
            from hdbscan import HDBSCAN

            labels = HDBSCAN(min_cluster_size=4).fit_predict(proj).tolist()
        except Exception:
            logger.debug("HDBSCAN failed on PCA projection", exc_info=True)
            labels = [-1] * proj.shape[0]
        n_clusters = len({int(label) for label in labels if label != -1})
        n_noise = sum(1 for label in labels if label == -1)
        pts = tuple(
            (float(p[0]), float(p[1]), int(lab)) for p, lab in zip(proj, labels, strict=True)
        )
        return ClusterScatterResult(points=pts, n_clusters=n_clusters, n_noise=n_noise)

    def _compute_monte_carlo(self) -> MonteCarloResult | None:
        """Stationary bootstrap of trajectory norm + VaR/CVaR at 95%.

        N=400 bootstrap samples of the mean over the recent window.
        Returns 5/25/50/75/95 percentiles for the fan chart.
        """
        recent = np.asarray(list(self._trajectory_lengths)[-200:], dtype=np.float64)
        if len(recent) < 20:
            return None
        rng = np.random.default_rng(seed=int(self._snapshot.tick) & 0xFFFF_FFFF)
        n_samples = 400
        means = np.empty(n_samples, dtype=np.float64)
        block_size = max(5, int(np.sqrt(len(recent))))
        for i in range(n_samples):
            # Stationary block bootstrap.
            starts = rng.integers(0, len(recent) - block_size, size=block_size)
            samples = recent[starts]
            means[i] = float(samples.mean())
        try:
            metrics = monte_carlo.var_cvar(recent, confidence=0.95)
        except Exception:
            logger.debug("var_cvar failed", exc_info=True)
            return None
        pct = {
            5: float(np.percentile(means, 5)),
            25: float(np.percentile(means, 25)),
            50: float(np.percentile(means, 50)),
            75: float(np.percentile(means, 75)),
            95: float(np.percentile(means, 95)),
        }
        return MonteCarloResult(
            percentiles=pct,
            var=float(metrics.var),
            cvar=float(metrics.cvar),
            n_samples=n_samples,
        )

    def _compute_pca(self) -> PCAResult | None:
        """PCA on the position history matrix.

        Returns top-K eigenvalues, their cumulative explained-variance
        ratio (scree plot input), and the loadings on PC1/PC2 for
        every agent.
        """
        if len(self._positions) < 10:
            return None
        matrix = np.stack(list(self._positions)[-30:])  # (T, A)
        if matrix.shape[1] < 2:
            return None
        x = matrix.T.astype(np.float64)  # (A, T)
        x = x - x.mean(axis=0, keepdims=True)
        try:
            _, s, _vt = np.linalg.svd(x, full_matrices=False)
        except np.linalg.LinAlgError:
            return None
        eigenvalues = (s**2) / max(x.shape[0] - 1, 1)
        total_var = float(eigenvalues.sum())
        if total_var == 0:
            return None
        explained = eigenvalues / total_var
        # Top 8 components for the scree plot.
        k = min(8, len(eigenvalues))
        top_eigs = tuple(float(e) for e in eigenvalues[:k])
        cum_var = tuple(float(c) for c in np.cumsum(explained[:k]))
        # PC1/PC2 loadings per agent come from vt[0,:] and vt[1,:],
        # but since rows = agents and cols = ticks, we want the score
        # of each agent on PC1/PC2. That's u[:,0]*s[0] / u[:,1]*s[1].
        try:
            u, sv, _ = np.linalg.svd(x, full_matrices=False)
            scores = u[:, :2] * sv[:2]
            loadings = tuple((float(row[0]), float(row[1])) for row in scores)
        except (np.linalg.LinAlgError, IndexError):
            loadings = ()
        return PCAResult(
            eigenvalues=top_eigs,
            explained_variance_ratio=cum_var,
            top2_loadings=loadings,
        )

    def _compute_arima_forecast(self) -> ArimaForecast | None:
        """AR(1) one-step forecast + 1.96·σ band, with the history series.

        We already compute arima_next as a scalar; this packages the
        last 60 observations and the std error so the frontend can
        draw an actual forecast band, not just print a number.
        """
        recent = list(self._trajectory_lengths)[-60:]
        if len(recent) < 30:
            return None
        values = np.asarray(recent, dtype=np.float64)
        try:
            forecast = time_series.arima_one_step(values, order=(1, 0, 0))
        except Exception:
            logger.debug("arima_forecast consumer raised", exc_info=True)
            return None
        return ArimaForecast(
            history=tuple(float(v) for v in values),
            next_value=float(forecast.next_value),
            next_std=float(forecast.forecast_std),
        )

    def _compute_logit(self) -> LogitResult | None:
        """Logistic regression P(y_t > median | y_{t-1}).

        Pedagogical demo of logit on the trajectory series. We
        construct treatment Y_t = 1{y_t > median(y)} and regress
        on the lag-1 feature y_{t-1}. The fit is by sklearn's
        LogisticRegression (L2-regularised), and we expose:
        - intercept α + slope β
        - 80 sampled points (x, σ(α + β·x)) for the curve
        - empirical (x, y) for the scatter underlay
        - McFadden's pseudo-R² (1 - log-lik / log-lik_null)
        """
        from sklearn.linear_model import LogisticRegression

        values = np.asarray(list(self._trajectory_lengths)[-200:], dtype=np.float64)
        if len(values) < 40:
            return None
        median = float(np.median(values))
        x = values[:-1].reshape(-1, 1)
        y = (values[1:] > median).astype(np.int64)
        if y.sum() < 5 or y.sum() > len(y) - 5:
            return None  # degenerate (everything one class)
        try:
            clf = LogisticRegression(max_iter=1000, C=1.0).fit(x, y)
        except Exception:
            logger.debug("logit fit failed", exc_info=True)
            return None
        slope = float(clf.coef_[0, 0])
        intercept = float(clf.intercept_[0])
        x_min, x_max = float(x.min()), float(x.max())
        pad = (x_max - x_min) * 0.1 if x_max > x_min else 1.0
        grid = np.linspace(x_min - pad, x_max + pad, 80)
        sig = 1.0 / (1.0 + np.exp(-(intercept + slope * grid)))
        curve = tuple((float(g), float(s)) for g, s in zip(grid, sig, strict=True))
        # Empirical scatter (sub-sampled for clarity).
        pts = tuple((float(xi[0]), int(yi)) for xi, yi in zip(x, y, strict=True))
        # McFadden's pseudo-R²
        try:
            proba = clf.predict_proba(x)[:, 1]
            eps = 1e-12
            ll_full = float(np.sum(y * np.log(proba + eps) + (1 - y) * np.log(1 - proba + eps)))
            p_null = float(y.mean())
            ll_null = float(np.sum(y * np.log(p_null + eps) + (1 - y) * np.log(1 - p_null + eps)))
            pseudo_r2 = 1.0 - ll_full / ll_null if ll_null != 0 else 0.0
        except Exception:
            pseudo_r2 = 0.0
        return LogitResult(
            intercept=intercept,
            slope=slope,
            curve=curve,
            points=pts,
            n=len(y),
            pseudo_r2=float(pseudo_r2),
        )

    def _compute_bayesian_posterior(self) -> BayesianPosterior | None:
        """Closed-form Beta posterior with full PDF curve.

        Beta(1, 1) prior + Binomial(n, θ) likelihood ⇒ Beta(1+s, 1+n-s)
        posterior. We sample the PDF at 100 θ ∈ [0, 1] points and
        also return mean / std / 95% credible interval.
        """
        from scipy.stats import beta

        values = list(self._trajectory_lengths)
        if not values:
            return None
        threshold = float(np.median(values))
        successes = int(sum(1 for v in values if v >= threshold))
        trials = len(values)
        alpha = 1.0 + successes
        bb = 1.0 + (trials - successes)
        rv = beta(alpha, bb)
        mean = float(rv.mean())
        std = float(rv.std())
        lo = float(rv.ppf(0.025))
        hi = float(rv.ppf(0.975))
        thetas = np.linspace(0.001, 0.999, 100)
        # scipy stubs return rv_discrete_frozen | rv_continuous_frozen
        # under the union; beta(α, β) is the continuous case which has
        # .pdf, but pyright can't narrow it without help.
        pdf = rv.pdf(thetas)  # pyright: ignore[reportAttributeAccessIssue]
        curve = tuple((float(t), float(p)) for t, p in zip(thetas, pdf, strict=True))
        return BayesianPosterior(
            alpha=alpha,
            beta=bb,
            mean=mean,
            std=std,
            credible_low=lo,
            credible_high=hi,
            curve=curve,
        )

    def _compute_granger(self) -> GrangerMatrix | None:
        """Pairwise Granger between 4 derived series from the buffers.

        Series (all length T, one per analytics tick):
          A. trajectory L₂ norm (raw)
          B. trajectory absolute first difference (volatility proxy)
          C. number of distinct nodes occupied per tick (dispersion proxy)
          D. heatmap entropy per tick (density spread)

        For each ordered pair (i, j) we report the p-value of the F
        test for the null 'i does NOT Granger-cause j' under lag = 2.
        """
        from statsmodels.tsa.stattools import grangercausalitytests

        traj = np.asarray(list(self._trajectory_lengths)[-100:], dtype=np.float64)
        if len(traj) < 40:
            return None
        diff = np.concatenate([[0.0], np.abs(np.diff(traj))])

        positions_list = list(self._positions)[-100:]
        dispersion = np.array(
            [float(len({int(p) for p in row.tolist()})) for row in positions_list],
            dtype=np.float64,
        )
        heatmaps = list(self._heatmaps)[-100:]
        if heatmaps:
            entropy_series = np.array(
                [
                    float(-np.sum((h / (h.sum() + 1e-12)) * np.log(h / (h.sum() + 1e-12) + 1e-12)))
                    for h in heatmaps
                ],
                dtype=np.float64,
            )
        else:
            entropy_series = np.zeros_like(traj)

        # Align lengths.
        n = min(len(traj), len(diff), len(dispersion), len(entropy_series))
        if n < 40:
            return None
        traj, diff = traj[-n:], diff[-n:]
        dispersion = dispersion[-n:]
        entropy_series = entropy_series[-n:]

        series = {"traj": traj, "vol": diff, "disp": dispersion, "entropy": entropy_series}
        names = ("traj", "vol", "disp", "entropy")
        k = len(names)
        p_mat: list[list[float]] = [[1.0] * k for _ in range(k)]
        max_lag = 2
        for i, ni in enumerate(names):
            for j, nj in enumerate(names):
                if i == j:
                    continue
                pair = np.column_stack([series[nj], series[ni]])  # [y, x]
                try:
                    result = grangercausalitytests(pair, maxlag=max_lag, verbose=False)
                    # statsmodels returns dict {lag: (tests, models)}.
                    # Use the F-test p-value at the chosen max lag.
                    p = float(result[max_lag][0]["ssr_ftest"][1])
                    p_mat[i][j] = p
                except Exception:
                    logger.debug("granger %s->%s failed", ni, nj, exc_info=True)
        return GrangerMatrix(
            series_names=names,
            p_values=tuple(tuple(row) for row in p_mat),
            max_lag=max_lag,
            n_obs=n,
        )

    def _compute_survival(self) -> SurvivalCurve | None:
        """Kaplan-Meier on recent match outcomes.

        Censored = match cut by `expired` reason; observed = `won`.
        Concept taught: KM is the non-parametric MLE of the survival
        function S(t) = P(T > t) under right-censoring.
        """
        from penumbra_analytics import survival

        outcomes = list(self._match_outcomes)
        if len(outcomes) < 5:
            return None
        durations = np.array([d for d, _ in outcomes], dtype=np.float64)
        events = np.array([e for _, e in outcomes], dtype=np.bool_)
        if events.sum() == 0:  # KM needs at least one observed event
            return None
        try:
            curve = survival.kaplan_meier(durations, events)
        except (ValueError, RuntimeError):
            logger.debug("KM fit failed", exc_info=True)
            return None
        # Median survival: the smallest t where S(t) ≤ 0.5.
        median: float | None = None
        for t, s in zip(curve.times, curve.survival, strict=True):
            if s <= 0.5:
                median = float(t)
                break
        return SurvivalCurve(
            times=tuple(float(t) for t in curve.times),
            survival=tuple(float(s) for s in curve.survival),
            confidence_low=tuple(float(c) for c in curve.confidence_low),
            confidence_high=tuple(float(c) for c in curve.confidence_high),
            n_events=int(events.sum()),
            n_censored=int(len(events) - events.sum()),
            median_time=median,
        )

    def _compute_spectral(self) -> SpectralReport | None:
        """Bottom-5 eigenvalues + Fiedler vector of the arena Laplacian.

        Concept taught: λ₂ (Fiedler) measures algebraic connectivity;
        the Fiedler EIGENVECTOR is the optimal continuous relaxation
        of the min-cut partition — sign(v_i) splits the graph in two.
        """
        from penumbra_analytics import linalg as analytics_linalg

        graph = self._arena_graph
        if graph is None:
            return None
        try:
            n_nodes = graph.number_of_nodes()  # type: ignore[attr-defined]
            n_edges = graph.number_of_edges()  # type: ignore[attr-defined]
            if n_nodes < 4:
                return None
            spec = analytics_linalg.spectral_embedding(graph, k=4)  # type: ignore[arg-type]
            fiedler = analytics_linalg.algebraic_connectivity(graph)  # type: ignore[arg-type]
        except (ValueError, RuntimeError):
            logger.debug("spectral compute failed", exc_info=True)
            return None
        # Fiedler vector = first column of the embedding (after the
        # constant has been dropped by spectral_embedding).
        fiedler_vec = spec.embedding[:, 0]
        return SpectralReport(
            eigenvalues=tuple(float(v) for v in spec.eigenvalues),
            fiedler_value=float(fiedler),
            n_nodes=int(n_nodes),
            n_edges=int(n_edges),
            fiedler_vector=tuple(float(v) for v in fiedler_vec),
        )

    def _compute_causal(self) -> CausalEstimate | None:
        """IPW + AIPW ATE: luxury-buyer treatment on trajectory norm.

        Builds a panel of (agent_id × window) observations:
        - treatment T = 1 iff the agent bought ≥1 luxury item in window
        - outcome Y = agent's trajectory L2 over the same window
        - covariate X = the agent's mean position over window
        """
        from penumbra_core.economy import PRODUCT_CATALOG

        from penumbra_analytics import causal as analytics_causal

        positions = list(self._positions)
        purchases = list(self._purchases)
        if len(positions) < 30 or not purchases:
            return None
        # Build per-agent aggregates over the window.
        position_matrix = np.stack(positions[-60:])  # (T, A)
        n_agents = position_matrix.shape[1]
        outcome = np.linalg.norm(position_matrix, axis=0)  # ‖x_a‖₂ across time
        covariate = position_matrix.mean(axis=0)  # average position per agent
        luxury_ids = {p.id for p in PRODUCT_CATALOG if p.category == "luxury"}
        treatment = np.zeros(n_agents, dtype=np.int64)
        for p in purchases:
            pid = int(getattr(p, "product_id", -1))
            aid = int(getattr(p, "agent_id", -1))
            if pid in luxury_ids and 0 <= aid < n_agents:
                treatment[aid] = 1
        n_treated = int(treatment.sum())
        n_control = int(n_agents - n_treated)
        if n_treated < 3 or n_control < 3:
            return None
        try:
            propensity = analytics_causal.estimate_propensity(treatment, covariate.reshape(-1, 1))
            ipw = analytics_causal.ipw_ate(outcome.astype(np.float64), treatment, propensity)
            aipw = analytics_causal.aipw_ate(
                outcome.astype(np.float64), treatment, covariate.reshape(-1, 1)
            )
        except (ValueError, np.linalg.LinAlgError):
            logger.debug("causal estimation failed", exc_info=True)
            return None
        return CausalEstimate(
            n_treated=n_treated,
            n_control=n_control,
            ipw_ate=float(ipw.ate),
            ipw_se=float(ipw.se),
            aipw_ate=float(aipw.ate),
            aipw_se=float(aipw.se),
            propensity_treated=tuple(float(p) for p in propensity[treatment == 1]),
            propensity_control=tuple(float(p) for p in propensity[treatment == 0]),
        )

    def _compute_var_irf(self) -> VARImpulseResponse | None:
        """Fit VAR(2) on (traj, vol, dispersion) and compute IRF.

        Returns the impulse-response matrix for the next 10 steps:
        irf[h][i][j] = response of j at step h to a 1-σ shock in i.
        """
        from statsmodels.tsa.api import VAR

        traj = np.asarray(list(self._trajectory_lengths)[-100:], dtype=np.float64)
        if len(traj) < 40:
            return None
        diff = np.concatenate([[0.0], np.abs(np.diff(traj))])
        positions_list = list(self._positions)[-100:]
        if not positions_list:
            return None
        dispersion = np.array(
            [float(len({int(p) for p in row.tolist()})) for row in positions_list],
            dtype=np.float64,
        )
        n = min(len(traj), len(diff), len(dispersion))
        if n < 40:
            return None
        series = np.column_stack([traj[-n:], diff[-n:], dispersion[-n:]])
        names = ("traj", "vol", "disp")
        try:
            model = VAR(series)
            fit = model.fit(maxlags=2, ic=None)
            irf = fit.irf(periods=10)
            irfs = np.asarray(irf.irfs)  # shape (11, n_series, n_series)
        except (ValueError, np.linalg.LinAlgError, ImportError):
            logger.debug("VAR/IRF failed", exc_info=True)
            return None
        # Re-pack: irf[h][i][j] = response of j to shock in i at step h.
        # statsmodels orientation is irfs[h, j, i] (response, shock). Convert.
        h, k, _ = irfs.shape
        out_irf: list[tuple[tuple[float, ...], ...]] = []
        for step in range(h):
            row_per_shock = []
            for i in range(k):
                responses = tuple(float(irfs[step, j, i]) for j in range(k))
                row_per_shock.append(responses)
            out_irf.append(tuple(row_per_shock))
        return VARImpulseResponse(
            series_names=names,
            horizon=h - 1,
            lag_order=int(fit.k_ar),
            irf=tuple(out_irf),
        )

    def _compute_garch(self) -> GarchResult | None:
        """Fit GARCH(1, 1) on the log-returns of the trajectory norm.

        Returns the estimated coefficients + the in-sample
        conditional volatility series.
        """
        from arch import arch_model

        traj = np.asarray(list(self._trajectory_lengths)[-200:], dtype=np.float64)
        if len(traj) < 60 or np.any(traj <= 0):
            return None
        # Centred log-returns (×100 so the optimiser doesn't underflow).
        returns = np.diff(np.log(traj)) * 100.0
        if len(returns) < 30 or np.std(returns) < 1e-6:
            return None
        try:
            am = arch_model(returns, mean="Zero", vol="GARCH", p=1, q=1, rescale=False)
            res = am.fit(disp="off", show_warning=False)
        except (ValueError, RuntimeError):
            logger.debug("GARCH fit failed", exc_info=True)
            return None
        # arch's res.params is a pandas Series; .get returns Any | None,
        # which pyright sees as possibly None.
        omega = float(res.params.get("omega", 0.0) or 0.0)  # type: ignore[arg-type]
        alpha = float(res.params.get("alpha[1]", 0.0) or 0.0)  # type: ignore[arg-type]
        beta = float(res.params.get("beta[1]", 0.0) or 0.0)  # type: ignore[arg-type]
        cond_vol = np.asarray(res.conditional_volatility, dtype=np.float64)
        return GarchResult(
            omega=omega,
            alpha=alpha,
            beta=beta,
            persistence=alpha + beta,
            log_returns=tuple(float(r) for r in returns),
            conditional_volatility=tuple(float(v) for v in cond_vol),
        )

    def _compute_qq_points(self) -> tuple[tuple[float, float], ...]:
        """Q-Q plot points for OLS residuals vs N(0, σ).

        Uses the residuals from the latest regression compute. Returns
        (theoretical_quantile, sample_quantile) sorted by theoretical.
        """
        from scipy.stats import norm

        reg = self._snapshot.regression
        if reg is None or len(reg.points) < 5:
            return ()
        # Recompute residuals from raw points and the fit.
        residuals = np.array(
            [y - (reg.intercept + reg.slope * x) for x, y in reg.points],
            dtype=np.float64,
        )
        residuals.sort()
        n = len(residuals)
        # Standardise to unit variance for the visual.
        sigma = float(np.std(residuals, ddof=1))
        if sigma < 1e-9:
            return ()
        standardised = residuals / sigma
        # Hazen plotting positions (i - 0.5) / n, classic for Q-Q.
        quantiles = np.array([(i + 0.5) / n for i in range(n)], dtype=np.float64)
        theoretical = norm.ppf(quantiles)
        return tuple((float(t), float(s)) for t, s in zip(theoretical, standardised, strict=True))

    def _compute_anova(self) -> ANOVAReport | None:
        """One-way ANOVA: trajectory norm grouped by HDBSCAN cluster.

        Requires at least 2 non-noise clusters with ≥ 2 members each.
        """
        if not self._snapshot.cluster_scatter:
            return None
        from penumbra_analytics import inferential

        scatter = self._snapshot.cluster_scatter
        # Build a per-agent (PC1 + PC2 norm) outcome and group by label.
        groups: dict[str, list[float]] = {}
        for x, y, label in scatter.points:
            if label < 0:
                continue
            key = f"c{label}"
            groups.setdefault(key, []).append(float(np.hypot(x, y)))
        valid = {k: np.asarray(v, dtype=np.float64) for k, v in groups.items() if len(v) >= 2}
        if len(valid) < 2:
            return None
        try:
            res = inferential.anova_oneway(valid)
        except (ValueError, RuntimeError):
            logger.debug("ANOVA failed", exc_info=True)
            return None
        return ANOVAReport(
            f_statistic=res.f_statistic,
            p_value=res.p_value,
            df_between=res.df_between,
            df_within=res.df_within,
            grouping="HDBSCAN cluster on PC1/PC2",
            group_names=res.group_names,
            group_means=res.group_means,
            group_se=res.group_se,
            group_n=res.group_n,
            grand_mean=res.grand_mean,
        )

    def _compute_autocorrelation(self) -> AutocorrelationReport | None:
        """ACF + PACF up to 20 lags on the trajectory series."""
        from statsmodels.tsa.stattools import acf, pacf

        values = np.asarray(list(self._trajectory_lengths)[-300:], dtype=np.float64)
        n = values.size
        if n < 40:
            return None
        try:
            max_lag = min(20, n // 3)
            a = acf(values, nlags=max_lag, fft=True)
            p = pacf(values, nlags=max_lag, method="ywm")
        except Exception:
            logger.debug("ACF/PACF failed", exc_info=True)
            return None
        band = 1.96 / np.sqrt(n)
        return AutocorrelationReport(
            n_obs=int(n),
            max_lag=int(max_lag),
            acf=tuple(float(v) for v in a),
            pacf=tuple(float(v) for v in p),
            conf_band=float(band),
        )

    def _compute_roc(self) -> ROCData | None:
        """ROC curve + AUC for the live logit classifier."""
        if not self._snapshot.logit:
            return None
        from sklearn.metrics import roc_auc_score, roc_curve

        logit = self._snapshot.logit
        # Re-derive the fit's predictions from the stored points and coefs.
        xs = np.array([x for x, _ in logit.points], dtype=np.float64)
        ys = np.array([y for _, y in logit.points], dtype=np.int64)
        if ys.sum() < 3 or ys.sum() > len(ys) - 3:
            return None
        proba = 1.0 / (1.0 + np.exp(-(logit.intercept + logit.slope * xs)))
        try:
            fpr, tpr, thresholds = roc_curve(ys, proba)
            auc = float(roc_auc_score(ys, proba))
        except (ValueError, RuntimeError):
            logger.debug("ROC failed", exc_info=True)
            return None
        # Down-sample to <=80 points so the wire stays compact.
        if len(fpr) > 80:
            idx = np.linspace(0, len(fpr) - 1, 80).astype(np.int64)
            fpr = fpr[idx]
            tpr = tpr[idx]
            thresholds = thresholds[idx]
        return ROCData(
            fpr=tuple(float(v) for v in fpr),
            tpr=tuple(float(v) for v in tpr),
            thresholds=tuple(float(v) for v in thresholds),
            auc=auc,
        )

    def _compute_correlations(self) -> CorrelationMatrix | None:
        """Pearson + Spearman matrix across derived metrics."""
        from scipy.stats import pearsonr, spearmanr

        traj = np.asarray(list(self._trajectory_lengths)[-200:], dtype=np.float64)
        if traj.size < 30:
            return None
        diff = np.concatenate([[0.0], np.abs(np.diff(traj))])
        squared = traj**2
        positions_list = list(self._positions)[-200:]
        if positions_list:
            disp = np.array(
                [float(len({int(p) for p in row.tolist()})) for row in positions_list],
                dtype=np.float64,
            )
        else:
            disp = np.zeros_like(traj)
        # Align lengths.
        n = min(traj.size, diff.size, squared.size, disp.size)
        if n < 30:
            return None
        series = {
            "traj": traj[-n:],
            "vol": diff[-n:],
            "traj²": squared[-n:],
            "disp": disp[-n:],
        }
        names = tuple(series.keys())
        k = len(names)
        pear = [[1.0] * k for _ in range(k)]
        spear = [[1.0] * k for _ in range(k)]
        for i, ni in enumerate(names):
            for j, nj in enumerate(names):
                if i >= j:
                    continue
                try:
                    # pearsonr returns a NamedTuple (statistic, pvalue);
                    # spearmanr returns SignificanceResult-ish; pyright's
                    # stub for spearmanr is over-loose, so coerce by index.
                    p_res = pearsonr(series[ni], series[nj])
                    s_res = spearmanr(series[ni], series[nj])
                    p_r = float(p_res[0])  # type: ignore[index]
                    s_r = float(s_res[0])  # type: ignore[index]
                except Exception:
                    p_r = s_r = 0.0
                pear[i][j] = pear[j][i] = p_r
                spear[i][j] = spear[j][i] = s_r
        return CorrelationMatrix(
            series_names=names,
            pearson=tuple(tuple(row) for row in pear),
            spearman=tuple(tuple(row) for row in spear),
            n_obs=int(n),
        )

    def _compute_permutation_test(self) -> PermutationReport | None:
        """Shuffle treatment labels n times, recompute IPW ATE under each.

        Returns the observed ATE + null distribution + 2-sided p.
        """
        from penumbra_core.economy import PRODUCT_CATALOG

        positions = list(self._positions)
        purchases = list(self._purchases)
        if len(positions) < 30 or not purchases:
            return None
        position_matrix = np.stack(positions[-60:])
        n_agents = position_matrix.shape[1]
        outcome = np.linalg.norm(position_matrix, axis=0)
        luxury_ids = {p.id for p in PRODUCT_CATALOG if p.category == "luxury"}
        treatment = np.zeros(n_agents, dtype=np.int64)
        for p in purchases:
            pid = int(getattr(p, "product_id", -1))
            aid = int(getattr(p, "agent_id", -1))
            if pid in luxury_ids and 0 <= aid < n_agents:
                treatment[aid] = 1
        n_t = int(treatment.sum())
        n_c = int(n_agents - n_t)
        if n_t < 3 or n_c < 3:
            return None
        # Observed: simple difference-in-means (faster + same null behaviour as IPW).
        observed = float(outcome[treatment == 1].mean() - outcome[treatment == 0].mean())
        n_perm = 250
        rng = np.random.default_rng(seed=(int(self._snapshot.tick) * 17) & 0xFFFFFFFF)
        null_samples = np.empty(n_perm, dtype=np.float64)
        for k in range(n_perm):
            perm = rng.permutation(treatment)
            null_samples[k] = outcome[perm == 1].mean() - outcome[perm == 0].mean()
        # Two-sided permutation p-value.
        p_two = float(np.mean(np.abs(null_samples) >= abs(observed)))
        return PermutationReport(
            observed_ate=observed,
            null_samples=tuple(float(v) for v in null_samples),
            p_two_sided=p_two,
            n_permutations=n_perm,
        )

    def _compute_candles(self) -> tuple[CandleSeries, ...]:
        """Per-product OHLC candles for the top-3 most-traded products.

        Bucket ticks into windows of `bucket_size`; within each bucket
        compute open (first trade price), high (max), low (min), close
        (last), and volume (sum quantity).
        """
        from penumbra_core.economy import PRODUCT_CATALOG

        if not self._trades:
            return ()
        recent = list(self._trades)[-1500:]
        # Group by product_id; pick top 3 by total volume.
        volume_by_pid: dict[int, int] = {}
        trades_by_pid: dict[int, list[object]] = {}
        for t in recent:
            pid = int(getattr(t, "product_id", -1))
            qty = int(getattr(t, "quantity", 0))
            volume_by_pid[pid] = volume_by_pid.get(pid, 0) + qty
            trades_by_pid.setdefault(pid, []).append(t)
        if not volume_by_pid:
            return ()
        top_pids = sorted(volume_by_pid, key=lambda p: -volume_by_pid[p])[:3]
        bucket_size = 20  # ticks per candle
        out: list[CandleSeries] = []
        for pid in top_pids:
            ts = sorted(trades_by_pid[pid], key=lambda t: int(getattr(t, "tick", 0)))
            buckets: dict[int, list[object]] = {}
            for t in ts:
                tick = int(getattr(t, "tick", 0))
                bucket = (tick // bucket_size) * bucket_size
                buckets.setdefault(bucket, []).append(t)
            candles: list[CandleBar] = []
            for bucket in sorted(buckets.keys()):
                bts = buckets[bucket]
                prices = [float(getattr(t, "unit_price", 0.0)) for t in bts]
                if not prices:
                    continue
                qty_total = sum(int(getattr(t, "quantity", 0)) for t in bts)
                candles.append(
                    CandleBar(
                        bucket=bucket,
                        open=prices[0],
                        high=max(prices),
                        low=min(prices),
                        close=prices[-1],
                        volume=qty_total,
                    )
                )
            if not candles:
                continue
            product = PRODUCT_CATALOG[pid] if 0 <= pid < len(PRODUCT_CATALOG) else None
            out.append(
                CandleSeries(
                    product_id=pid,
                    product_name=product.name if product else f"#{pid}",
                    category=product.category if product else "?",
                    candles=tuple(candles[-30:]),
                    total_volume=int(volume_by_pid[pid]),
                    bucket_ticks=bucket_size,
                )
            )
        return tuple(out)

    def _compute_inflation(self) -> InflationSeries | None:
        if len(self._cpi_history) < 2:
            return None
        return InflationSeries(
            cpi=tuple(self._cpi_history),
            money_supply=tuple(self._money_supply_history),
            n_samples=len(self._cpi_history),
        )

    def _compute_wealth(self) -> WealthReport | None:
        """Lorenz curve + Gini from the latest wealth snapshot."""
        try:
            wealth = list(self._latest_wealth)
            if len(wealth) < 5:
                return None
            arr = np.asarray(sorted(wealth), dtype=np.float64)
            n = arr.size
            total = float(arr.sum())
            if total <= 0:
                return None
            # Lorenz curve: cumulative population share vs cumulative wealth share.
            cum = np.cumsum(arr)
            lorenz_x = np.arange(1, n + 1) / n
            lorenz_y = cum / total
            # Gini = 1 - 2 × area under Lorenz (trapezoid rule).
            # numpy 2.x renamed trapz → trapezoid; both exist with the
            # latter being preferred.
            trapezoid = getattr(np, "trapezoid", None) or getattr(np, "trapz", None)
            if trapezoid is None:
                return None
            area = float(trapezoid(lorenz_y, lorenz_x))
            gini = float(1.0 - 2.0 * area)
            # Percentile snapshot.
            p10 = float(np.percentile(arr, 10))
            p50 = float(np.percentile(arr, 50))
            p90 = float(np.percentile(arr, 90))
            p99 = float(np.percentile(arr, 99))
        except Exception:
            logger.warning("wealth consumer failed", exc_info=True)
            return None
        return WealthReport(
            lorenz_x=tuple(float(v) for v in lorenz_x),
            lorenz_y=tuple(float(v) for v in lorenz_y),
            gini=max(0.0, min(1.0, gini)),
            p10=p10,
            p50=p50,
            p90=p90,
            p99=p99,
            total_wealth=total,
            n_agents=n,
        )

    def _compute_residual_vs_fitted(self) -> tuple[tuple[float, float], ...]:
        """Residual-vs-fitted scatter points for the OLS regression."""
        reg = self._snapshot.regression
        if reg is None or len(reg.points) < 5:
            return ()
        return tuple(
            (
                float(reg.intercept + reg.slope * x),
                float(y - (reg.intercept + reg.slope * x)),
            )
            for x, y in reg.points
        )

    # ── internals ───────────────────────────────────────────────────

    def _due(self, now: float, key: str) -> bool:
        return now - self._last_run.get(key, 0.0) >= self.cadences.get(key, 1.0)

    def _with_tick(self, tick: int) -> DashboardSnapshot:
        """Bump the snapshot tick while preserving every other field."""
        snapshot = self._snapshot
        snapshot.tick = tick
        return snapshot


def _bars_payload(diagram: NDArray[np.float64]) -> tuple[tuple[float, float], ...]:
    """Convert a ripser persistence diagram into a JSON-friendly tuple of pairs.

    Infinite deaths (the global connected component lives forever) are
    clamped to the max finite death in the diagram + a small margin so
    the frontend can render them as the right edge of the chart. If
    the diagram has only infinite intervals, we clamp to 1.0.
    """
    if diagram.size == 0:
        return ()
    finite_mask = np.isfinite(diagram[:, 1])
    finite_max = float(diagram[finite_mask, 1].max()) if finite_mask.any() else 1.0
    bars: list[tuple[float, float]] = []
    for birth, death in diagram.tolist():
        death_clamped = float(death) if np.isfinite(death) else finite_max * 1.05
        bars.append((float(birth), death_clamped))
    # Sort by descending lifetime so the most persistent bars come first.
    bars.sort(key=lambda b: b[0] - b[1])  # negative lifetime → longest first
    return tuple(bars)
