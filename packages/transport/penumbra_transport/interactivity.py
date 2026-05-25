"""Helpers backing the interactivity endpoints in :mod:`api`.

Concept taught: serialisation + chart-export plumbing for the
"click-to-inspect", "step-through-debug", and "download-as-CSV / JSON /
PNG / notebook" surfaces on the dashboard. Pure, side-effect-free
functions; the FastAPI handlers in :mod:`penumbra_transport.api` are the
only callers and they own all I/O.

The module deliberately stays adapter-shaped: every public function takes
already-extracted plain values (lists of pairs, agent objects, dicts of
auxiliary chart context, etc.) and returns a JSON-friendly dict or
bytes. No FastAPI types here, so unit tests can drive the functions
directly.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

logger = logging.getLogger(__name__)


class InteractivityError(Exception):
    """Base class for errors raised by the interactivity helpers."""


class UnsupportedMetricError(InteractivityError):
    """Raised when an export is requested for an unknown metric kind."""


# Original tabular metrics. These flow through the standard "columns +
# rows" CSV/JSON renderer and the legacy line-chart PNG renderer.
TABULAR_METRICS: tuple[str, ...] = (
    "inflation",
    "garch",
    "training_curves",
    "wealth",
    "candles",
    "mempool",
    "chain_height",
)

# Phase-bonus metrics with bespoke chart shapes (bar charts, heatmaps,
# scatter plots, multi-series IRF grids). They still expose CSV + JSON
# via the same intermediate "columns + rows" shape, but their PNG
# rendering branches on a per-metric ``chart_kind`` so the user gets a
# real labeled chart rather than the postage-stamp client capture.
EXTENDED_METRICS: tuple[str, ...] = (
    "trajectory_mean",
    "trajectory_std",
    "hdbscan_clusters",
    "dp_epsilon_spent",
    "signing_verified",
    "pca",
    "logit",
    "granger",
    "economy",
    "survival",
    "spectral",
    "causal",
    "var_irf",
    "anova",
    "autocorrelation",
    "correlations",
    "permutation",
    "vrf_leader",
    "kyber_kem",
    "multi_checkpoint",
    "value_map",
    "gat_attention",
    "arena_graph",
)

SUPPORTED_METRICS: tuple[str, ...] = TABULAR_METRICS + EXTENDED_METRICS

SUPPORTED_FORMATS: tuple[str, ...] = ("csv", "json", "png")


# Chart kinds dispatched inside :func:`render_png`. The intermediate
# payload sets ``chart_kind`` so the renderer doesn't have to re-grok
# the metric semantics.
CHART_KIND_LINE = "line"
CHART_KIND_BAR = "bar"
CHART_KIND_GROUPED_BAR = "grouped_bar"
CHART_KIND_SCATTER_FIT = "scatter_fit"
CHART_KIND_SCATTER_LABELED = "scatter_labeled"
CHART_KIND_HEATMAP = "heatmap"
CHART_KIND_HIST = "hist"
CHART_KIND_MULTI_LINE = "multi_line"


# ── deterministic agent name synthesis ─────────────────────────────

_ADJECTIVES: tuple[str, ...] = (
    "amber",
    "brisk",
    "calm",
    "dusty",
    "eager",
    "frosty",
    "gilded",
    "hidden",
    "iron",
    "jolly",
    "keen",
    "lucid",
    "misty",
    "noble",
    "opal",
    "pale",
    "quiet",
    "ruby",
    "swift",
    "tidal",
    "umber",
    "vivid",
    "wry",
    "xenon",
    "young",
    "zesty",
)
_NOUNS: tuple[str, ...] = (
    "fox",
    "owl",
    "lynx",
    "raven",
    "stag",
    "wolf",
    "hawk",
    "otter",
    "vole",
    "crane",
    "newt",
    "mole",
    "kite",
    "moth",
    "wren",
    "tern",
    "shrew",
    "marten",
    "weasel",
    "badger",
)


def agent_name_for(agent_id: int) -> str:
    """Return a stable, human-readable handle for an agent id.

    The mapping is pure: same id -> same name across processes. Used by
    the /agents listing so the dashboard can show "amber fox" instead
    of "agent 0".
    """
    adj = _ADJECTIVES[agent_id % len(_ADJECTIVES)]
    noun = _NOUNS[(agent_id // len(_ADJECTIVES)) % len(_NOUNS)]
    return f"{adj} {noun}"


# ── chart-data extraction ──────────────────────────────────────────


def chart_series(
    metric: str,
    *,
    dashboard_snapshot: object | None,
    training_samples: Sequence[Any] | None,
    chain_height: int | None,
    mempool_size: int | None,
    extra_context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Project an arbitrary dashboard slice into a flat exportable form.

    Returns ``{"metric", "generated_at_tick", "columns", "rows",
    "chart_kind", "title"?, "x_label"?, "y_label"?, "extras"?}``.
    ``rows`` is a list of dicts keyed by ``columns``; both CSV + JSON
    renderers consume that same intermediate shape. The PNG renderer
    branches on ``chart_kind`` and ``extras`` to produce a properly
    labeled chart at 800x400 px rather than the postage-stamp client
    capture.

    ``extra_context`` carries auxiliary payloads that the bonus metrics
    need (VRF leader history, value-map dict, gat-attention matrix,
    signing stats, dp budget, arena topology). Tabular metrics ignore
    it.
    """
    if metric not in SUPPORTED_METRICS:
        raise UnsupportedMetricError(
            f"unsupported metric: {metric!r}; supported = {list(SUPPORTED_METRICS)}"
        )
    tick = int(getattr(dashboard_snapshot, "tick", 0)) if dashboard_snapshot is not None else 0
    ctx = dict(extra_context or {})

    if metric in TABULAR_METRICS:
        return _tabular_payload(
            metric,
            dashboard_snapshot=dashboard_snapshot,
            training_samples=training_samples,
            chain_height=chain_height,
            mempool_size=mempool_size,
            tick=tick,
        )
    return _extended_payload(metric, dashboard_snapshot=dashboard_snapshot, tick=tick, ctx=ctx)


def _empty(
    metric: str,
    tick: int,
    *,
    columns: Sequence[str],
    chart_kind: str = CHART_KIND_LINE,
    title: str | None = None,
) -> dict[str, object]:
    return {
        "metric": metric,
        "generated_at_tick": tick,
        "columns": list(columns),
        "rows": [],
        "chart_kind": chart_kind,
        "title": title or metric,
    }


# ── tabular metrics (legacy 7) ─────────────────────────────────────


def _tabular_payload(
    metric: str,
    *,
    dashboard_snapshot: object | None,
    training_samples: Sequence[Any] | None,
    chain_height: int | None,
    mempool_size: int | None,
    tick: int,
) -> dict[str, object]:
    if metric == "inflation":
        inflation = getattr(dashboard_snapshot, "inflation", None)
        if inflation is None:
            return _empty(metric, tick, columns=("tick", "cpi", "money_supply"))
        cpi = list(getattr(inflation, "cpi", ()))
        money = list(getattr(inflation, "money_supply", ()))
        rows: list[dict[str, object]] = []
        for i in range(min(len(cpi), len(money))):
            t = float(cpi[i][0])
            rows.append(
                {
                    "tick": t,
                    "cpi": float(cpi[i][1]),
                    "money_supply": float(money[i][1]),
                }
            )
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["tick", "cpi", "money_supply"],
            "rows": rows,
            "chart_kind": CHART_KIND_LINE,
            "title": "CPI + money supply",
            "x_label": "tick",
        }
    if metric == "garch":
        garch = getattr(dashboard_snapshot, "garch", None)
        if garch is None:
            return _empty(metric, tick, columns=("step", "log_return", "conditional_vol"))
        log_returns = list(getattr(garch, "log_returns", ()))
        cond_vol = list(getattr(garch, "conditional_volatility", ()))
        rows = []
        for i in range(min(len(log_returns), len(cond_vol))):
            rows.append(
                {
                    "step": int(i),
                    "log_return": float(log_returns[i]),
                    "conditional_vol": float(cond_vol[i]),
                }
            )
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["step", "log_return", "conditional_vol"],
            "rows": rows,
            "chart_kind": CHART_KIND_LINE,
            "title": "GARCH(1,1) conditional volatility",
            "x_label": "step",
        }
    if metric == "training_curves":
        if not training_samples:
            return _empty(
                metric,
                tick,
                columns=("iteration", "actor_loss", "critic_loss", "entropy", "kl", "mean_reward"),
            )
        rows = []
        for s in training_samples:
            rows.append(
                {
                    "iteration": int(getattr(s, "iteration", 0)),
                    "actor_loss": float(getattr(s, "actor_loss", 0.0)),
                    "critic_loss": float(getattr(s, "critic_loss", 0.0)),
                    "entropy": float(getattr(s, "entropy", 0.0)),
                    "kl": float(getattr(s, "kl", 0.0)),
                    "mean_reward": float(getattr(s, "mean_reward", 0.0)),
                }
            )
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": [
                "iteration",
                "actor_loss",
                "critic_loss",
                "entropy",
                "kl",
                "mean_reward",
            ],
            "rows": rows,
            "chart_kind": CHART_KIND_LINE,
            "title": "MAPPO training curves",
            "x_label": "iteration",
        }
    if metric == "wealth":
        wealth = getattr(dashboard_snapshot, "wealth", None)
        if wealth is None:
            return _empty(metric, tick, columns=("lorenz_x", "lorenz_y"))
        xs = list(getattr(wealth, "lorenz_x", ()))
        ys = list(getattr(wealth, "lorenz_y", ()))
        rows = [
            {"lorenz_x": float(xs[i]), "lorenz_y": float(ys[i])}
            for i in range(min(len(xs), len(ys)))
        ]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["lorenz_x", "lorenz_y"],
            "rows": rows,
            "chart_kind": CHART_KIND_LINE,
            "title": "Wealth Lorenz curve",
            "x_label": "cumulative agent share",
            "y_label": "cumulative wealth share",
        }
    if metric == "candles":
        candle_series = list(getattr(dashboard_snapshot, "candles", ()) or ())
        rows = []
        for cs in candle_series:
            product_id = getattr(cs, "product_id", "?")
            for c in getattr(cs, "candles", ()) or ():
                rows.append(
                    {
                        "product_id": str(product_id),
                        "bucket": int(getattr(c, "bucket", 0)),
                        "open": float(getattr(c, "open", 0.0)),
                        "high": float(getattr(c, "high", 0.0)),
                        "low": float(getattr(c, "low", 0.0)),
                        "close": float(getattr(c, "close", 0.0)),
                        "volume": float(getattr(c, "volume", 0.0)),
                    }
                )
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["product_id", "bucket", "open", "high", "low", "close", "volume"],
            "rows": rows,
            "chart_kind": CHART_KIND_LINE,
            "title": "Candles (OHLC per product)",
            "x_label": "bucket",
        }
    if metric == "mempool":
        rows = [{"tick": tick, "mempool_size": int(mempool_size or 0)}]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["tick", "mempool_size"],
            "rows": rows,
            "chart_kind": CHART_KIND_LINE,
            "title": "mempool size",
        }
    # chain_height
    rows = [{"tick": tick, "chain_height": int(chain_height or 0)}]
    return {
        "metric": metric,
        "generated_at_tick": tick,
        "columns": ["tick", "chain_height"],
        "rows": rows,
        "chart_kind": CHART_KIND_LINE,
        "title": "chain height",
    }


# ── extended metrics ───────────────────────────────────────────────


def _extended_payload(
    metric: str,
    *,
    dashboard_snapshot: object | None,
    tick: int,
    ctx: Mapping[str, object],
) -> dict[str, object]:
    snap = dashboard_snapshot
    if metric == "trajectory_mean":
        regression = getattr(snap, "regression", None)
        if regression is None:
            return _empty(
                metric,
                tick,
                columns=("tick", "trajectory_norm"),
                chart_kind=CHART_KIND_SCATTER_FIT,
                title="trajectory mean - OLS fit",
            )
        points = list(getattr(regression, "points", ()) or ())
        rows = [{"tick": float(p[0]), "trajectory_norm": float(p[1])} for p in points]
        slope = float(getattr(regression, "slope", 0.0))
        intercept = float(getattr(regression, "intercept", 0.0))
        sigma = float(getattr(regression, "sigma", 0.0))
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["tick", "trajectory_norm"],
            "rows": rows,
            "chart_kind": CHART_KIND_SCATTER_FIT,
            "title": "trajectory mean - OLS fit (alpha + beta*t)",
            "x_label": "tick",
            "y_label": "trajectory L2 norm",
            "extras": {
                "slope": slope,
                "intercept": intercept,
                "sigma": sigma,
                "r_squared": float(getattr(regression, "r_squared", 0.0)),
                "n": int(getattr(regression, "n", 0)),
            },
        }
    if metric == "trajectory_std":
        garch = getattr(snap, "garch", None)
        if garch is None:
            return _empty(
                metric,
                tick,
                columns=("step", "conditional_vol"),
                title="trajectory dispersion (GARCH sigma_t)",
            )
        cond_vol = list(getattr(garch, "conditional_volatility", ()))
        rows = [{"step": int(i), "conditional_vol": float(v)} for i, v in enumerate(cond_vol)]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["step", "conditional_vol"],
            "rows": rows,
            "chart_kind": CHART_KIND_LINE,
            "title": "trajectory dispersion - GARCH sigma_t",
            "x_label": "step",
            "y_label": "sigma_t",
        }
    if metric == "hdbscan_clusters":
        scatter = getattr(snap, "cluster_scatter", None)
        if scatter is None:
            return _empty(
                metric,
                tick,
                columns=("pc1", "pc2", "label"),
                chart_kind=CHART_KIND_SCATTER_LABELED,
                title="HDBSCAN clusters on PC1/PC2",
            )
        points = list(getattr(scatter, "points", ()) or ())
        rows = [{"pc1": float(p[0]), "pc2": float(p[1]), "label": int(p[2])} for p in points]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["pc1", "pc2", "label"],
            "rows": rows,
            "chart_kind": CHART_KIND_SCATTER_LABELED,
            "title": "HDBSCAN clusters on PC1/PC2",
            "x_label": "PC1",
            "y_label": "PC2",
            "extras": {
                "n_clusters": int(getattr(scatter, "n_clusters", 0)),
                "n_noise": int(getattr(scatter, "n_noise", 0)),
            },
        }
    if metric == "dp_epsilon_spent":
        dp = ctx.get("dp_budget")
        if not isinstance(dp, dict):
            return _empty(
                metric,
                tick,
                columns=("phase", "epsilon"),
                chart_kind=CHART_KIND_BAR,
                title="DP epsilon budget",
            )
        spent = float(dp.get("epsilon_spent", 0.0))
        total = float(dp.get("epsilon_total", 0.0))
        remaining = float(dp.get("epsilon_remaining", max(0.0, total - spent)))
        rows = [
            {"phase": "spent", "epsilon": spent},
            {"phase": "remaining", "epsilon": remaining},
            {"phase": "total", "epsilon": total},
        ]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["phase", "epsilon"],
            "rows": rows,
            "chart_kind": CHART_KIND_BAR,
            "title": "Differential-privacy epsilon spent",
            "x_label": "phase",
            "y_label": "epsilon",
        }
    if metric == "signing_verified":
        stats = ctx.get("signing_stats")
        if not isinstance(stats, dict):
            return _empty(
                metric,
                tick,
                columns=("outcome", "count"),
                chart_kind=CHART_KIND_BAR,
                title="Dilithium signatures",
            )
        verified = int(stats.get("verified", 0))
        rejected = int(stats.get("rejected", 0))
        rows = [
            {"outcome": "verified", "count": verified},
            {"outcome": "rejected", "count": rejected},
        ]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["outcome", "count"],
            "rows": rows,
            "chart_kind": CHART_KIND_BAR,
            "title": "Dilithium signature outcomes",
            "x_label": "outcome",
            "y_label": "cumulative count",
        }
    if metric == "pca":
        pca = getattr(snap, "pca", None)
        if pca is None:
            return _empty(
                metric,
                tick,
                columns=("component", "eigenvalue", "cumulative_variance"),
                chart_kind=CHART_KIND_BAR,
                title="PCA eigenvalues + cumulative variance",
            )
        eigs = list(getattr(pca, "eigenvalues", ()) or ())
        evr = list(getattr(pca, "explained_variance_ratio", ()) or ())
        cum = []
        running = 0.0
        for v in evr:
            running += float(v)
            cum.append(running)
        rows = []
        for i, e in enumerate(eigs):
            rows.append(
                {
                    "component": i + 1,
                    "eigenvalue": float(e),
                    "cumulative_variance": float(cum[i]) if i < len(cum) else 0.0,
                }
            )
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["component", "eigenvalue", "cumulative_variance"],
            "rows": rows,
            "chart_kind": CHART_KIND_BAR,
            "title": "PCA - eigenvalues + cumulative variance",
            "x_label": "component",
            "y_label": "eigenvalue",
            "extras": {"overlay_line_col": "cumulative_variance", "kaiser_line": 1.0},
        }
    if metric == "logit":
        logit = getattr(snap, "logit", None)
        if logit is None:
            return _empty(
                metric,
                tick,
                columns=("x", "p"),
                chart_kind=CHART_KIND_LINE,
                title="Logistic regression - propensity",
            )
        curve = list(getattr(logit, "curve", ()) or ())
        rows = [{"x": float(p[0]), "p": float(p[1])} for p in curve]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["x", "p"],
            "rows": rows,
            "chart_kind": CHART_KIND_LINE,
            "title": "Logistic regression - propensity sigmoid",
            "x_label": "x (lag-1 trajectory norm)",
            "y_label": "P(y_t > median | x)",
            "extras": {
                "slope": float(getattr(logit, "slope", 0.0)),
                "intercept": float(getattr(logit, "intercept", 0.0)),
                "pseudo_r2": float(getattr(logit, "pseudo_r2", 0.0)),
            },
        }
    if metric == "granger":
        granger = getattr(snap, "granger", None)
        if granger is None:
            return _empty(
                metric,
                tick,
                columns=("row", "col", "p_value"),
                chart_kind=CHART_KIND_HEATMAP,
                title="Granger causality matrix",
            )
        names = list(getattr(granger, "series_names", ()) or ())
        matrix = [list(row) for row in getattr(granger, "p_values", ()) or ()]
        rows = []
        for i, r_name in enumerate(names):
            for j, c_name in enumerate(names):
                rows.append(
                    {"row": str(r_name), "col": str(c_name), "p_value": float(matrix[i][j])}
                )
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["row", "col", "p_value"],
            "rows": rows,
            "chart_kind": CHART_KIND_HEATMAP,
            "title": "Granger causality - p(row does NOT cause col)",
            "x_label": "consequent (column)",
            "y_label": "antecedent (row)",
            "extras": {"labels": names, "matrix": matrix, "value_label": "p-value"},
        }
    if metric == "economy":
        econ = getattr(snap, "economy", None)
        if econ is None:
            return _empty(
                metric,
                tick,
                columns=("product", "units", "revenue"),
                chart_kind=CHART_KIND_BAR,
                title="Economy - top products",
            )
        top = list(getattr(econ, "top_products", ()) or ())
        rows = [
            {
                "product": str(p[0]),
                "units": int(p[1]),
                "revenue": float(p[2]) if len(p) > 2 else 0.0,
            }
            for p in top
        ]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["product", "units", "revenue"],
            "rows": rows,
            "chart_kind": CHART_KIND_BAR,
            "title": "City economy - top products (units sold)",
            "x_label": "product",
            "y_label": "units",
        }
    if metric == "survival":
        surv = getattr(snap, "survival", None)
        if surv is None:
            return _empty(
                metric,
                tick,
                columns=("t", "survival", "ci_low", "ci_high"),
                title="Kaplan-Meier survival curve",
            )
        times = list(getattr(surv, "times", ()) or ())
        s = list(getattr(surv, "survival", ()) or ())
        lo = list(getattr(surv, "confidence_low", ()) or ())
        hi = list(getattr(surv, "confidence_high", ()) or ())
        rows = []
        n = min(len(times), len(s))
        for i in range(n):
            rows.append(
                {
                    "t": float(times[i]),
                    "survival": float(s[i]),
                    "ci_low": float(lo[i]) if i < len(lo) else float(s[i]),
                    "ci_high": float(hi[i]) if i < len(hi) else float(s[i]),
                }
            )
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["t", "survival", "ci_low", "ci_high"],
            "rows": rows,
            "chart_kind": CHART_KIND_LINE,
            "title": "Kaplan-Meier survival curve",
            "x_label": "tick",
            "y_label": "P(still running)",
        }
    if metric == "spectral":
        spectral = getattr(snap, "spectral", None)
        if spectral is None:
            return _empty(
                metric,
                tick,
                columns=("index", "eigenvalue"),
                chart_kind=CHART_KIND_BAR,
                title="Laplacian spectrum",
            )
        eigs = list(getattr(spectral, "eigenvalues", ()) or ())
        rows = [{"index": i + 1, "eigenvalue": float(v)} for i, v in enumerate(eigs)]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["index", "eigenvalue"],
            "rows": rows,
            "chart_kind": CHART_KIND_BAR,
            "title": "Normalised Laplacian - bottom eigenvalues",
            "x_label": "index",
            "y_label": "eigenvalue",
            "extras": {"fiedler_value": float(getattr(spectral, "fiedler_value", 0.0))},
        }
    if metric == "causal":
        causal = getattr(snap, "causal", None)
        if causal is None:
            return _empty(
                metric,
                tick,
                columns=("estimator", "ate", "se"),
                chart_kind=CHART_KIND_BAR,
                title="Causal ATE - IPW + AIPW",
            )
        rows = [
            {
                "estimator": "IPW",
                "ate": float(getattr(causal, "ipw_ate", 0.0)),
                "se": float(getattr(causal, "ipw_se", 0.0)),
            },
            {
                "estimator": "AIPW",
                "ate": float(getattr(causal, "aipw_ate", 0.0)),
                "se": float(getattr(causal, "aipw_se", 0.0)),
            },
        ]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["estimator", "ate", "se"],
            "rows": rows,
            "chart_kind": CHART_KIND_BAR,
            "title": "Causal ATE - IPW vs AIPW",
            "x_label": "estimator",
            "y_label": "ATE (95% CI = +/-1.96*SE)",
            "extras": {"error_col": "se"},
        }
    if metric == "var_irf":
        varirf = getattr(snap, "var_irf", None)
        if varirf is None:
            return _empty(
                metric,
                tick,
                columns=("horizon", "shock", "response", "value"),
                chart_kind=CHART_KIND_MULTI_LINE,
                title="VAR impulse responses",
            )
        names = list(getattr(varirf, "series_names", ()) or [])
        irf = getattr(varirf, "irf", ()) or ()
        rows = []
        for h, step in enumerate(irf):
            for i, src in enumerate(names):
                for j, dst in enumerate(names):
                    try:
                        v = float(step[i][j])
                    except (IndexError, TypeError, ValueError):
                        v = 0.0
                    rows.append(
                        {
                            "horizon": int(h),
                            "shock": str(src),
                            "response": str(dst),
                            "value": v,
                        }
                    )
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["horizon", "shock", "response", "value"],
            "rows": rows,
            "chart_kind": CHART_KIND_MULTI_LINE,
            "title": "VAR impulse responses",
            "x_label": "horizon",
            "y_label": "response",
            "extras": {"series_names": names},
        }
    if metric == "anova":
        anova = getattr(snap, "anova", None)
        if anova is None:
            return _empty(
                metric,
                tick,
                columns=("group", "mean", "se"),
                chart_kind=CHART_KIND_BAR,
                title="ANOVA - per-group means",
            )
        names = list(getattr(anova, "group_names", ()) or [])
        means = list(getattr(anova, "group_means", ()) or [])
        ses = list(getattr(anova, "group_se", ()) or [])
        rows = []
        for i, n_name in enumerate(names):
            rows.append(
                {
                    "group": str(n_name),
                    "mean": float(means[i]) if i < len(means) else 0.0,
                    "se": float(ses[i]) if i < len(ses) else 0.0,
                }
            )
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["group", "mean", "se"],
            "rows": rows,
            "chart_kind": CHART_KIND_BAR,
            "title": "ANOVA - per-cluster mean (+/- SE)",
            "x_label": "cluster",
            "y_label": "PC norm",
            "extras": {
                "error_col": "se",
                "grand_mean": float(getattr(anova, "grand_mean", 0.0)),
            },
        }
    if metric == "autocorrelation":
        acorr = getattr(snap, "autocorrelation", None)
        if acorr is None:
            return _empty(
                metric,
                tick,
                columns=("lag", "acf", "pacf"),
                chart_kind=CHART_KIND_GROUPED_BAR,
                title="ACF + PACF",
            )
        acf = list(getattr(acorr, "acf", ()) or [])
        pacf = list(getattr(acorr, "pacf", ()) or [])
        rows = []
        n = max(len(acf), len(pacf))
        for i in range(n):
            rows.append(
                {
                    "lag": int(i),
                    "acf": float(acf[i]) if i < len(acf) else 0.0,
                    "pacf": float(pacf[i]) if i < len(pacf) else 0.0,
                }
            )
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["lag", "acf", "pacf"],
            "rows": rows,
            "chart_kind": CHART_KIND_GROUPED_BAR,
            "title": "Autocorrelation (ACF) + Partial ACF",
            "x_label": "lag",
            "y_label": "correlation",
            "extras": {"conf_band": float(getattr(acorr, "conf_band", 0.0))},
        }
    if metric == "correlations":
        corr = getattr(snap, "correlations", None)
        if corr is None:
            return _empty(
                metric,
                tick,
                columns=("row", "col", "pearson", "spearman"),
                chart_kind=CHART_KIND_HEATMAP,
                title="Correlation matrix",
            )
        names = list(getattr(corr, "series_names", ()) or [])
        pearson = [list(r) for r in getattr(corr, "pearson", ()) or []]
        spearman = [list(r) for r in getattr(corr, "spearman", ()) or []]
        rows = []
        for i, r_name in enumerate(names):
            for j, c_name in enumerate(names):
                rows.append(
                    {
                        "row": str(r_name),
                        "col": str(c_name),
                        "pearson": float(pearson[i][j]),
                        "spearman": float(spearman[i][j]) if spearman else 0.0,
                    }
                )
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["row", "col", "pearson", "spearman"],
            "rows": rows,
            "chart_kind": CHART_KIND_HEATMAP,
            "title": "Pearson correlation matrix",
            "x_label": "column",
            "y_label": "row",
            "extras": {"labels": names, "matrix": pearson, "value_label": "Pearson r"},
        }
    if metric == "permutation":
        perm = getattr(snap, "permutation", None)
        if perm is None:
            return _empty(
                metric,
                tick,
                columns=("sample",),
                chart_kind=CHART_KIND_HIST,
                title="Permutation null distribution",
            )
        samples = list(getattr(perm, "null_samples", ()) or [])
        rows = [{"sample": float(v)} for v in samples]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["sample"],
            "rows": rows,
            "chart_kind": CHART_KIND_HIST,
            "title": "Permutation test - null ATE distribution",
            "x_label": "shuffled ATE",
            "y_label": "frequency",
            "extras": {
                "observed_ate": float(getattr(perm, "observed_ate", 0.0)),
                "p_two_sided": float(getattr(perm, "p_two_sided", 0.0)),
            },
        }
    if metric == "vrf_leader":
        vrf = ctx.get("vrf_leader")
        if not isinstance(vrf, dict):
            return _empty(
                metric,
                tick,
                columns=("validator", "wins"),
                chart_kind=CHART_KIND_BAR,
                title="VRF leader frequency",
            )
        recent = vrf.get("recent", []) or []
        counts: dict[int, int] = {}
        if isinstance(recent, list):
            for blk in recent:
                if not isinstance(blk, dict):
                    continue
                idx_raw = blk.get("leader_index", -1)
                try:
                    idx = int(idx_raw)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
                if idx >= 0:
                    counts[idx] = counts.get(idx, 0) + 1
        rows = [{"validator": f"v{idx}", "wins": int(c)} for idx, c in sorted(counts.items())]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["validator", "wins"],
            "rows": rows,
            "chart_kind": CHART_KIND_BAR,
            "title": "VRF leader-frequency (last N blocks)",
            "x_label": "validator",
            "y_label": "blocks led",
        }
    if metric == "kyber_kem":
        kyber = ctx.get("kyber_demo")
        if not isinstance(kyber, dict):
            return _empty(
                metric,
                tick,
                columns=("artifact", "size_bytes"),
                chart_kind=CHART_KIND_BAR,
                title="Kyber ML-KEM-768 sizes",
            )
        rows = [
            {"artifact": "public_key", "size_bytes": int(kyber.get("public_key_size", 0))},
            {"artifact": "secret_key", "size_bytes": int(kyber.get("secret_key_size", 0))},
            {"artifact": "ciphertext", "size_bytes": int(kyber.get("ciphertext_size", 0))},
            {
                "artifact": "shared_secret",
                "size_bytes": int(kyber.get("shared_secret_size", 0)),
            },
        ]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["artifact", "size_bytes"],
            "rows": rows,
            "chart_kind": CHART_KIND_BAR,
            "title": "Kyber ML-KEM-768 - artifact sizes",
            "x_label": "artifact",
            "y_label": "bytes",
        }
    if metric == "multi_checkpoint":
        mc = ctx.get("multi_checkpoint")
        if not isinstance(mc, dict) or not mc.get("available"):
            return _empty(
                metric,
                tick,
                columns=("agent_id", "kl"),
                chart_kind=CHART_KIND_BAR,
                title="Multi-checkpoint KL per agent",
            )
        per_agent = mc.get("per_agent_kl", []) or []
        rows: list[dict[str, object]] = []
        if isinstance(per_agent, list):
            for i, v in enumerate(per_agent):
                try:
                    rows.append({"agent_id": int(i), "kl": float(v)})
                except (TypeError, ValueError):
                    continue
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["agent_id", "kl"],
            "rows": rows,
            "chart_kind": CHART_KIND_BAR,
            "title": "MAPPO A/B - KL(primary || side) per agent",
            "x_label": "agent_id",
            "y_label": "KL divergence",
            "extras": {
                "mean_kl": float(mc.get("mean_kl", 0.0)),
                "max_kl": float(mc.get("max_kl", 0.0)),
                "agreement_rate": float(mc.get("agreement_rate", 0.0)),
            },
        }
    if metric == "value_map":
        vm = ctx.get("value_map")
        if not isinstance(vm, dict) or not vm.get("available"):
            return _empty(
                metric,
                tick,
                columns=("agent_id", "entropy", "top_prob"),
                chart_kind=CHART_KIND_BAR,
                title="Value map - per-agent entropy",
            )
        per_agent = vm.get("per_agent", []) or []
        rows = []
        if isinstance(per_agent, list):
            for row in per_agent:
                if not isinstance(row, dict):
                    continue
                rows.append(
                    {
                        "agent_id": int(row.get("agent_id", 0)),
                        "entropy": float(row.get("entropy", 0.0)),
                        "top_prob": float(row.get("top_prob", 0.0)),
                    }
                )
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["agent_id", "entropy", "top_prob"],
            "rows": rows,
            "chart_kind": CHART_KIND_BAR,
            "title": "Value map - actor entropy per agent",
            "x_label": "agent_id",
            "y_label": "entropy",
            "extras": {"v_state": float(vm.get("v_state", 0.0))},
        }
    if metric == "gat_attention":
        gat = ctx.get("gat_attention")
        if not isinstance(gat, dict) or not gat.get("available"):
            return _empty(
                metric,
                tick,
                columns=("from", "to", "weight"),
                chart_kind=CHART_KIND_HEATMAP,
                title="GATv2 layer-1 attention",
            )
        attn_raw = gat.get("attention_layer1", []) or []
        node_ids = gat.get("node_ids", []) or []
        matrix: list[list[float]] = []
        if isinstance(attn_raw, list):
            for r in attn_raw:
                if isinstance(r, list):
                    matrix.append([float(v) for v in r])
        labels: list[str] = []
        if isinstance(node_ids, list):
            labels = [str(int(nid)) for nid in node_ids]
        rows = []
        for i, src in enumerate(labels):
            for j, dst in enumerate(labels):
                if i < len(matrix) and j < len(matrix[i]):
                    rows.append({"from": src, "to": dst, "weight": float(matrix[i][j])})
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["from", "to", "weight"],
            "rows": rows,
            "chart_kind": CHART_KIND_HEATMAP,
            "title": "GATv2 - layer-1 attention weights",
            "x_label": "to node",
            "y_label": "from node",
            "extras": {"labels": labels, "matrix": matrix, "value_label": "attention"},
        }
    if metric == "arena_graph":
        topo = ctx.get("arena_topology")
        if not isinstance(topo, dict):
            return _empty(
                metric,
                tick,
                columns=("degree", "count"),
                chart_kind=CHART_KIND_BAR,
                title="Arena - node degree distribution",
            )
        nodes_raw = topo.get("nodes", []) or []
        edges_raw = topo.get("edges", []) or []
        degrees: dict[int, int] = {}
        if isinstance(nodes_raw, list):
            for nid in nodes_raw:
                try:
                    degrees[int(nid)] = 0
                except (TypeError, ValueError):
                    continue
        if isinstance(edges_raw, list):
            for e in edges_raw:
                if not isinstance(e, dict):
                    continue
                try:
                    u, v = int(e.get("u")), int(e.get("v"))  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
                degrees[u] = degrees.get(u, 0) + 1
                degrees[v] = degrees.get(v, 0) + 1
        histogram: dict[int, int] = {}
        for d in degrees.values():
            histogram[d] = histogram.get(d, 0) + 1
        rows = [{"degree": int(d), "count": int(c)} for d, c in sorted(histogram.items())]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["degree", "count"],
            "rows": rows,
            "chart_kind": CHART_KIND_BAR,
            "title": "Arena graph - node degree distribution",
            "x_label": "degree",
            "y_label": "count",
        }
    # Unreachable: SUPPORTED_METRICS guards above.
    raise UnsupportedMetricError(f"extended metric {metric!r} has no handler")


# ── rendering ──────────────────────────────────────────────────────


def render_csv(payload: dict[str, object]) -> bytes:
    """Render the intermediate dict to a CSV byte string with a header row."""
    columns = list(payload.get("columns", []))  # type: ignore[arg-type]
    rows = list(payload.get("rows", []))  # type: ignore[arg-type]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for row in rows:
        if isinstance(row, dict):
            writer.writerow([row.get(col, "") for col in columns])
    return buf.getvalue().encode("utf-8")


def render_json(payload: dict[str, object]) -> bytes:
    """Render the intermediate dict to a compact JSON byte string."""
    out = {
        "metric": payload.get("metric"),
        "generated_at_tick": payload.get("generated_at_tick"),
        "data": payload.get("rows", []),
    }
    return json.dumps(out, separators=(",", ":")).encode("utf-8")


def render_png(payload: dict[str, object]) -> bytes:
    """Render the intermediate dict to an 800x400 PNG chart.

    Dispatches on ``payload["chart_kind"]``: line / bar / grouped_bar /
    scatter_fit / scatter_labeled / heatmap / hist / multi_line. Each
    renderer adds title, axis labels, grid, and a legend where useful.

    Raises :class:`InteractivityError` if matplotlib is not importable;
    the caller is expected to map that to HTTP 503.
    """
    try:
        import matplotlib
    except ImportError as exc:
        raise InteractivityError("matplotlib not available") from exc
    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    columns = list(payload.get("columns", []))  # type: ignore[arg-type]
    rows = list(payload.get("rows", []))  # type: ignore[arg-type]
    metric_name = str(payload.get("metric", "metric"))
    chart_kind = str(payload.get("chart_kind", CHART_KIND_LINE))
    title = str(payload.get("title", metric_name))
    x_label = payload.get("x_label")
    y_label = payload.get("y_label")
    extras_raw = payload.get("extras") or {}
    extras: dict[str, object] = dict(extras_raw) if isinstance(extras_raw, dict) else {}

    fig, ax = plt.subplots(figsize=(8, 4), dpi=100)

    if not rows:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)
    elif chart_kind == CHART_KIND_BAR:
        _render_bar(ax, columns, rows, extras)
    elif chart_kind == CHART_KIND_GROUPED_BAR:
        _render_grouped_bar(ax, columns, rows, extras)
    elif chart_kind == CHART_KIND_SCATTER_FIT:
        _render_scatter_fit(ax, columns, rows, extras)
    elif chart_kind == CHART_KIND_SCATTER_LABELED:
        _render_scatter_labeled(ax, columns, rows)
    elif chart_kind == CHART_KIND_HEATMAP:
        _render_heatmap(fig, ax, extras)
    elif chart_kind == CHART_KIND_HIST:
        _render_hist(ax, columns, rows, extras)
    elif chart_kind == CHART_KIND_MULTI_LINE:
        _render_multi_line(ax, rows, extras)
    else:
        _render_line(ax, columns, rows)

    ax.set_title(title)
    if x_label is not None:
        ax.set_xlabel(str(x_label))
    if y_label is not None:
        ax.set_ylabel(str(y_label))
    if chart_kind != CHART_KIND_HEATMAP:
        ax.grid(True, alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def _row_floats(rows: Sequence[dict[str, object]], col: str) -> list[float]:
    out: list[float] = []
    for r in rows:
        try:
            out.append(float(r.get(col, 0)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            out.append(0.0)
    return out


def _row_strs(rows: Sequence[dict[str, object]], col: str) -> list[str]:
    return [str(r.get(col, "")) for r in rows]


def _render_line(ax: Any, columns: Sequence[str], rows: Sequence[dict[str, object]]) -> None:
    x_col = columns[0] if columns else None
    x_values: list[float] = (
        _row_floats(rows, x_col) if x_col is not None else list(range(len(rows)))
    )
    plotted = False
    for col in columns[1:]:
        ys = _row_floats(rows, col)
        if any(y != 0.0 for y in ys) or len(ys) > 1:
            ax.plot(x_values, ys, label=col)
            plotted = True
    if plotted:
        ax.legend(fontsize="x-small", loc="best")


def _render_bar(
    ax: Any,
    columns: Sequence[str],
    rows: Sequence[dict[str, object]],
    extras: Mapping[str, object],
) -> None:
    if not columns or len(columns) < 2:
        return
    label_col = columns[0]
    value_col = columns[1]
    labels = _row_strs(rows, label_col)
    values = _row_floats(rows, value_col)
    error_col = extras.get("error_col")
    errors: list[float] | None = None
    if isinstance(error_col, str) and error_col in columns:
        ses = _row_floats(rows, error_col)
        errors = [1.96 * s for s in ses]
    xs = list(range(len(labels)))
    ax.bar(xs, values, color="#3fb6c8", yerr=errors, capsize=3 if errors else 0)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    overlay = extras.get("overlay_line_col")
    if isinstance(overlay, str) and overlay in columns:
        ax2 = ax.twinx()
        ys = _row_floats(rows, overlay)
        ax2.plot(xs, ys, color="#d97a4a", marker="o", linewidth=1.5, label=overlay)
        ax2.set_ylabel(overlay)
        ax2.legend(fontsize="x-small", loc="upper left")
    kaiser = extras.get("kaiser_line")
    if isinstance(kaiser, int | float):
        ax.axhline(float(kaiser), color="#d97a4a", linestyle="--", linewidth=1, alpha=0.7)
    grand = extras.get("grand_mean")
    if isinstance(grand, int | float):
        ax.axhline(
            float(grand),
            color="#d97a4a",
            linestyle="--",
            linewidth=1,
            alpha=0.7,
            label="grand mean",
        )
        ax.legend(fontsize="x-small", loc="best")


def _render_grouped_bar(
    ax: Any,
    columns: Sequence[str],
    rows: Sequence[dict[str, object]],
    extras: Mapping[str, object],
) -> None:
    if len(columns) < 3:
        return
    label_col = columns[0]
    series_cols = list(columns[1:])
    labels = _row_strs(rows, label_col)
    n = len(labels)
    n_series = len(series_cols)
    width = 0.8 / max(1, n_series)
    base = list(range(n))
    palette = ["#3fb6c8", "#d97a4a", "#8aa39b", "#c8b53f"]
    for i, col in enumerate(series_cols):
        ys = _row_floats(rows, col)
        xs = [b + i * width - 0.4 + width / 2 for b in base]
        ax.bar(xs, ys, width=width, label=col, color=palette[i % len(palette)])
    ax.set_xticks(base)
    ax.set_xticklabels(labels, fontsize=8)
    ax.legend(fontsize="x-small", loc="best")
    band = extras.get("conf_band")
    if isinstance(band, int | float) and band > 0:
        ax.axhline(float(band), color="#888888", linestyle="--", linewidth=0.8)
        ax.axhline(-float(band), color="#888888", linestyle="--", linewidth=0.8)


def _render_scatter_fit(
    ax: Any,
    columns: Sequence[str],
    rows: Sequence[dict[str, object]],
    extras: Mapping[str, object],
) -> None:
    if len(columns) < 2:
        return
    xs = _row_floats(rows, columns[0])
    ys = _row_floats(rows, columns[1])
    ax.scatter(xs, ys, s=12, color="#3fb6c8", alpha=0.7, label="observations")
    slope = float(extras.get("slope", 0.0))  # type: ignore[arg-type]
    intercept = float(extras.get("intercept", 0.0))  # type: ignore[arg-type]
    sigma = float(extras.get("sigma", 0.0))  # type: ignore[arg-type]
    if xs:
        x_min, x_max = min(xs), max(xs)
        line_x = [x_min, x_max]
        line_y = [intercept + slope * x_min, intercept + slope * x_max]
        ax.plot(line_x, line_y, color="#d97a4a", linewidth=1.5, label="OLS fit")
        if sigma > 0:
            band = 1.96 * sigma
            ax.fill_between(
                line_x,
                [y - band for y in line_y],
                [y + band for y in line_y],
                color="#d97a4a",
                alpha=0.15,
                label="+/-1.96 sigma",
            )
    r2 = extras.get("r_squared")
    if isinstance(r2, int | float):
        ax.text(
            0.02,
            0.95,
            f"R^2 = {float(r2):.3f}",
            transform=ax.transAxes,
            fontsize=9,
            verticalalignment="top",
        )
    ax.legend(fontsize="x-small", loc="best")


def _render_scatter_labeled(
    ax: Any, columns: Sequence[str], rows: Sequence[dict[str, object]]
) -> None:
    if len(columns) < 3:
        return
    xs = _row_floats(rows, columns[0])
    ys = _row_floats(rows, columns[1])
    labels = [int(r.get(columns[2], -1)) for r in rows]  # type: ignore[arg-type]
    unique = sorted(set(labels))
    palette = ["#3fb6c8", "#d97a4a", "#8aa39b", "#c8b53f", "#a16ec8", "#6ec88a"]
    for k, lab in enumerate(unique):
        idx = [i for i, lb in enumerate(labels) if lb == lab]
        color = "#666666" if lab == -1 else palette[k % len(palette)]
        legend = "noise" if lab == -1 else f"cluster {lab}"
        ax.scatter(
            [xs[i] for i in idx],
            [ys[i] for i in idx],
            s=14,
            color=color,
            alpha=0.75,
            label=legend,
        )
    ax.legend(fontsize="x-small", loc="best")


def _render_heatmap(fig: Any, ax: Any, extras: Mapping[str, object]) -> None:
    matrix_raw = extras.get("matrix")
    labels_raw = extras.get("labels")
    value_label = str(extras.get("value_label", "value"))
    if not isinstance(matrix_raw, list) or not matrix_raw:
        ax.text(0.5, 0.5, "no matrix", ha="center", va="center", transform=ax.transAxes)
        return
    matrix = [[float(v) for v in row] for row in matrix_raw]
    n_rows = len(matrix)
    n_cols = len(matrix[0]) if matrix else 0
    labels: list[str] = []
    if isinstance(labels_raw, list):
        labels = [str(label) for label in labels_raw]
    im = ax.imshow(matrix, aspect="auto", cmap="viridis")
    if labels and len(labels) == n_cols:
        ax.set_xticks(list(range(n_cols)))
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    if labels and len(labels) == n_rows:
        ax.set_yticks(list(range(n_rows)))
        ax.set_yticklabels(labels, fontsize=8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(value_label, fontsize=8)


def _render_hist(
    ax: Any,
    columns: Sequence[str],
    rows: Sequence[dict[str, object]],
    extras: Mapping[str, object],
) -> None:
    if not columns:
        return
    values = _row_floats(rows, columns[0])
    if not values:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)
        return
    bins = max(10, min(40, int(math.sqrt(len(values)))))
    ax.hist(values, bins=bins, color="#3fb6c8", alpha=0.85, edgecolor="#173b40")
    obs = extras.get("observed_ate")
    if isinstance(obs, int | float):
        ax.axvline(
            float(obs),
            color="#d97a4a",
            linestyle="--",
            linewidth=1.5,
            label=f"observed = {float(obs):.3f}",
        )
        ax.legend(fontsize="x-small", loc="best")


def _render_multi_line(
    ax: Any, rows: Sequence[dict[str, object]], extras: Mapping[str, object]
) -> None:
    by_pair: dict[tuple[str, str], list[tuple[int, float]]] = {}
    for r in rows:
        shock = str(r.get("shock", ""))
        resp = str(r.get("response", ""))
        try:
            h = int(r.get("horizon", 0))  # type: ignore[arg-type]
            v = float(r.get("value", 0.0))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        by_pair.setdefault((shock, resp), []).append((h, v))
    if not by_pair:
        return
    palette = ["#3fb6c8", "#d97a4a", "#8aa39b", "#c8b53f", "#a16ec8", "#6ec88a", "#c83f7a"]
    for k, ((shock, resp), pts) in enumerate(sorted(by_pair.items())):
        pts.sort(key=lambda p: p[0])
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, label=f"{shock}->{resp}", color=palette[k % len(palette)])
    ax.legend(fontsize="x-small", loc="best", ncol=2)


# ── Jupyter notebook generation ────────────────────────────────────


def build_export_notebook(
    metric: str,
    *,
    api_base: str = "http://localhost:8100",
) -> bytes:
    """Build a tiny nbformat-shaped .ipynb that fetches + plots `metric`.

    We hand-roll the JSON (rather than depend on ``nbformat``) because
    the notebook format is a small fixed schema and adding a runtime
    dependency just for one endpoint isn't worth it.
    """
    if metric not in SUPPORTED_METRICS:
        raise UnsupportedMetricError(
            f"unsupported metric: {metric!r}; supported = {list(SUPPORTED_METRICS)}"
        )
    url = f"{api_base}/export/chart/{metric}?format=json"
    code = (
        "import json\n"
        "import urllib.request\n"
        "import matplotlib.pyplot as plt\n"
        "\n"
        f"URL = {url!r}\n"
        "with urllib.request.urlopen(URL) as resp:\n"
        "    payload = json.loads(resp.read().decode('utf-8'))\n"
        "data = payload.get('data', [])\n"
        "if not data:\n"
        "    print('no data for metric:', payload.get('metric'))\n"
        "else:\n"
        "    cols = list(data[0].keys())\n"
        "    x_col = cols[0]\n"
        "    xs = [row[x_col] for row in data]\n"
        "    fig, ax = plt.subplots(figsize=(8, 4))\n"
        "    for col in cols[1:]:\n"
        "        ax.plot(xs, [row[col] for row in data], label=col)\n"
        "    ax.set_title(payload.get('metric', 'metric'))\n"
        "    ax.legend()\n"
        "    plt.show()\n"
    )
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [f"# Penumbra - exported {metric}\n"],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": code.splitlines(keepends=True),
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    f"Live dashboard: <{api_base.replace('8100', '5173')}/>\n",
                ],
            },
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
            "penumbra": {
                "metric": metric,
                "generated_wall_ns": int(time.time_ns()),
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, indent=1).encode("utf-8")


# ── crypto fingerprints for the agent-detail endpoint ──────────────


def short_fingerprint(material: bytes, *, length: int = 16) -> str:
    """Return a short hex SHA-256 fingerprint of arbitrary public-key bytes."""
    if not material:
        return ""
    digest = hashlib.sha256(material).hexdigest()
    return digest[:length]
