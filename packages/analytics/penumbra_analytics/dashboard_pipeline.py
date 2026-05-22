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
    inferential,
    monte_carlo,
    time_series,
    topics,
    topology,
)
from penumbra_analytics import transport as analytics_transport

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
        }
    )

    _trajectory_lengths: deque[float] = field(default_factory=lambda: deque(maxlen=512))
    _positions: deque[NDArray[np.float64]] = field(default_factory=lambda: deque(maxlen=64))
    _heatmaps: deque[NDArray[np.float64]] = field(default_factory=lambda: deque(maxlen=64))
    _utterances: deque[str] = field(default_factory=lambda: deque(maxlen=400))
    _purchases: deque[object] = field(default_factory=lambda: deque(maxlen=2000))
    _purchases_by_tick: deque[int] = field(default_factory=lambda: deque(maxlen=2000))
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


def _unused_inferential_import() -> object:
    """statsmodels'/inferential's import dependency for downstream consumers."""
    return inferential  # keeps the linter from complaining about the unused import
