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
    topology,
)
from penumbra_analytics import transport as analytics_transport

logger = logging.getLogger(__name__)


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
        }
    )

    _trajectory_lengths: deque[float] = field(default_factory=lambda: deque(maxlen=512))
    _positions: deque[NDArray[np.float64]] = field(default_factory=lambda: deque(maxlen=64))
    _heatmaps: deque[NDArray[np.float64]] = field(default_factory=lambda: deque(maxlen=64))
    _last_run: dict[str, float] = field(default_factory=dict)
    _snapshot: DashboardSnapshot = field(default_factory=lambda: DashboardSnapshot(tick=-1))

    def observe(
        self,
        *,
        tick: int,
        positions: NDArray[np.float64],
        heatmap: NDArray[np.float64] | None = None,
    ) -> None:
        """Push a tick's observation into the rolling buffers."""
        self._snapshot = (
            DashboardSnapshot(tick=tick) if self._snapshot.tick == -1 else self._with_tick(tick)
        )
        self._trajectory_lengths.append(float(np.linalg.norm(positions)))
        self._positions.append(np.asarray(positions, dtype=np.float64))
        if heatmap is not None:
            self._heatmaps.append(np.asarray(heatmap, dtype=np.float64))

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
                logger.debug("consumer raised on the current window; will retry next cadence", exc_info=True)
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

        return self._snapshot

    @property
    def snapshot(self) -> DashboardSnapshot:
        return self._snapshot

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
