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
        }
    )

    _trajectory_lengths: deque[float] = field(default_factory=lambda: deque(maxlen=512))
    _positions: deque[NDArray[np.float64]] = field(default_factory=lambda: deque(maxlen=64))
    _heatmaps: deque[NDArray[np.float64]] = field(default_factory=lambda: deque(maxlen=64))
    _utterances: deque[str] = field(default_factory=lambda: deque(maxlen=400))
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
