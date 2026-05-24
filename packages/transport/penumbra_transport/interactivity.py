"""Helpers backing the interactivity endpoints in :mod:`api`.

Concept taught: serialisation + chart-export plumbing for the
"click-to-inspect", "step-through-debug", and "download-as-CSV / JSON /
PNG / notebook" surfaces on the dashboard. Pure, side-effect-free
functions; the FastAPI handlers in :mod:`penumbra_transport.api` are the
only callers and they own all I/O.

The module deliberately stays adapter-shaped: every public function takes
already-extracted plain values (lists of pairs, agent objects, etc.) and
returns a JSON-friendly dict or bytes. No FastAPI types here, so unit
tests can drive the functions directly.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class InteractivityError(Exception):
    """Base class for errors raised by the interactivity helpers."""


class UnsupportedMetricError(InteractivityError):
    """Raised when an export is requested for an unknown metric kind."""


class UnsupportedFormatError(InteractivityError):
    """Raised when an export format is not one of csv / json / png."""


SUPPORTED_METRICS: tuple[str, ...] = (
    "inflation",
    "garch",
    "training_curves",
    "wealth",
    "candles",
    "mempool",
    "chain_height",
)

SUPPORTED_FORMATS: tuple[str, ...] = ("csv", "json", "png")


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

    The mapping is pure: same id → same name across processes. Used by
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
) -> dict[str, object]:
    """Project an arbitrary dashboard slice into a flat exportable form.

    Returns ``{"metric", "generated_at_tick", "columns", "rows"}`` where
    ``rows`` is a list of dicts keyed by ``columns``. Both CSV + JSON
    + PNG renderers consume this same intermediate shape so the metric
    list lives in one place.
    """
    if metric not in SUPPORTED_METRICS:
        raise UnsupportedMetricError(
            f"unsupported metric: {metric!r}; supported = {list(SUPPORTED_METRICS)}"
        )
    tick = int(getattr(dashboard_snapshot, "tick", 0)) if dashboard_snapshot is not None else 0
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
        }
    if metric == "mempool":
        rows = [{"tick": tick, "mempool_size": int(mempool_size or 0)}]
        return {
            "metric": metric,
            "generated_at_tick": tick,
            "columns": ["tick", "mempool_size"],
            "rows": rows,
        }
    # chain_height
    rows = [{"tick": tick, "chain_height": int(chain_height or 0)}]
    return {
        "metric": metric,
        "generated_at_tick": tick,
        "columns": ["tick", "chain_height"],
        "rows": rows,
    }


def _empty(metric: str, tick: int, *, columns: Sequence[str]) -> dict[str, object]:
    return {
        "metric": metric,
        "generated_at_tick": tick,
        "columns": list(columns),
        "rows": [],
    }


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
    """Render the intermediate dict to a 600x300 PNG line chart.

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
    fig, ax = plt.subplots(figsize=(6, 3), dpi=100)
    if not rows:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)
    else:
        # Plot every numeric column except the first (x-axis).
        x_col = columns[0] if columns else None
        x_values: list[float] = []
        if x_col is not None:
            for r in rows:
                try:
                    x_values.append(float(r.get(x_col, 0)))
                except (TypeError, ValueError):
                    x_values.append(0.0)
        else:
            x_values = list(range(len(rows)))
        for col in columns[1:]:
            ys: list[float] = []
            for r in rows:
                try:
                    ys.append(float(r.get(col, 0)))
                except (TypeError, ValueError):
                    ys.append(0.0)
            if any(y != 0.0 for y in ys) or len(ys) > 1:
                ax.plot(x_values, ys, label=col)
        if any(col for col in columns[1:]):
            ax.legend(fontsize="x-small", loc="best")
    ax.set_title(metric_name)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


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
                "source": [f"# Penumbra — exported {metric}\n"],
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
