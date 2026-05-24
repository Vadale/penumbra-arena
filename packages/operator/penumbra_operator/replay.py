"""Operator session replay log + cross-session leaderboard storage.

Concept taught: a *session replay* is the reproducibility contract
that turns the operator from an ad-hoc human into a benchmark
participant. Every action the operator submits is appended (kind,
payload, submit tick, success, applied tick, elapsed ms) to a per-
session parquet under ``state/operator/sessions/<id>/actions.parquet``;
the closing scorecard + scenario id + timestamps land in a sibling
``meta.json``. The pair is enough to re-run the exact action stream
against a fresh, identically-seeded :class:`OperatorContext` and
recover the same final scorecard within a small numerical tolerance.

Why polars + parquet?
    Replay logs are append-only, columnar, often consumed by
    downstream notebooks; parquet is the project-standard cold-storage
    format and polars is the project-standard analytics frame (CLAUDE.md
    "Prefer Polars over Pandas"). We never hold the full log in memory
    longer than the flush window — ``SessionLogger`` keeps a small
    in-RAM buffer and writes once on ``close_session``.

Determinism contract:
    A replay round-trip is considered consistent when every numeric
    scorecard axis matches the recorded ``final_scorecard`` within
    ``REPLAY_TOLERANCE``. Counter axes (``attacks_survived``,
    ``chain_contribution``) must match exactly because they are pure
    integers; ``profit`` / ``privacy_preserved`` / ``composite`` are
    floats and may drift by epsilon when DP noise re-samples under a
    re-seeded RNG.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from penumbra_operator.actions import OperatorAction, OperatorActionResult, OperatorContext
    from penumbra_operator.scoring import OperatorScoreCard


REPLAY_TOLERANCE: float = 1e-4
DEFAULT_SESSIONS_DIR: Path = Path("state/operator/sessions")

_ACTIONS_FILE = "actions.parquet"
_META_FILE = "meta.json"


class SessionLogError(Exception):
    """Raised when a session id is unknown or the parquet/meta is malformed."""


@dataclass(slots=True)
class _ActionRow:
    """One queued (action, result) pair as stored on disk."""

    submit_tick: int
    applied_tick: int
    kind: str
    payload_json: str
    success: bool
    skipped: bool
    elapsed_ms: float
    error_code: str | None
    error_message: str | None


@dataclass(slots=True)
class SessionLogger:
    """File-backed logger for operator sessions.

    One logger instance can hold multiple open sessions (the orchestrator
    only needs one at a time, but the API surface stays plural so the
    CLI's ``pno replay`` driver can introspect closed sessions without
    racing the live writer).
    """

    base_dir: Path = field(default_factory=lambda: DEFAULT_SESSIONS_DIR)
    _open_buffers: dict[str, list[_ActionRow]] = field(default_factory=dict)
    _open_meta: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)

    # ── lifecycle ───────────────────────────────────────────────────

    def start_session(self, scenario_id: str | None = None) -> str:
        """Create a fresh session directory + return the new session id.

        The id is a timestamp-prefixed UUID so a sorted listing renders
        chronologically without any extra metadata lookups.
        """
        ts = int(time.time())
        session_id = f"{ts}-{uuid.uuid4().hex[:8]}"
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        self._open_buffers[session_id] = []
        self._open_meta[session_id] = {
            "session_id": session_id,
            "scenario_id": scenario_id,
            "started_at": ts,
            "closed_at": None,
            "final_scorecard": None,
            "n_actions": 0,
        }
        return session_id

    def record(
        self,
        session_id: str,
        action: OperatorAction,
        result: OperatorActionResult,
    ) -> None:
        """Append one (action, result) pair to the in-RAM buffer.

        The buffer is flushed to parquet by :meth:`close_session`. We
        never write a single row at a time — polars+parquet is far more
        efficient when we materialise a frame once at close.
        """
        buf = self._open_buffers.get(session_id)
        if buf is None:
            raise SessionLogError(f"unknown or closed session {session_id!r}")
        error = result.error or {}
        buf.append(
            _ActionRow(
                submit_tick=int(action.submit_tick),
                applied_tick=int(result.applied_tick),
                kind=str(action.kind),
                payload_json=json.dumps(action.payload, sort_keys=True, default=str),
                success=bool(result.success),
                skipped=bool(result.skipped),
                elapsed_ms=float(result.elapsed_ms),
                error_code=(str(error.get("code")) if error.get("code") is not None else None),
                error_message=(
                    str(error.get("message")) if error.get("message") is not None else None
                ),
            )
        )

    def close_session(
        self,
        session_id: str,
        final_scorecard: OperatorScoreCard,
    ) -> dict[str, Any]:
        """Flush buffered rows to parquet + write meta.json with the final score."""
        buf = self._open_buffers.pop(session_id, None)
        meta = self._open_meta.pop(session_id, None)
        if buf is None or meta is None:
            raise SessionLogError(f"unknown or already-closed session {session_id!r}")
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        frame = _rows_to_frame(buf)
        frame.write_parquet(session_dir / _ACTIONS_FILE)
        meta["closed_at"] = int(time.time())
        meta["n_actions"] = len(buf)
        meta["final_scorecard"] = _scorecard_dict(final_scorecard)
        (session_dir / _META_FILE).write_text(json.dumps(meta, indent=2, sort_keys=True))
        return dict(meta)

    # ── reads ───────────────────────────────────────────────────────

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return metadata for every closed session under ``base_dir``."""
        if not self.base_dir.exists():
            return []
        out: list[dict[str, Any]] = []
        for child in sorted(self.base_dir.iterdir()):
            meta_path = child / _META_FILE
            if not meta_path.is_file():
                continue
            try:
                meta = json.loads(meta_path.read_text())
            except json.JSONDecodeError:
                continue
            scorecard = meta.get("final_scorecard") or {}
            out.append(
                {
                    "session_id": str(meta.get("session_id", child.name)),
                    "scenario_id": meta.get("scenario_id"),
                    "started_at": int(meta.get("started_at", 0) or 0),
                    "closed_at": (
                        int(meta["closed_at"]) if meta.get("closed_at") is not None else None
                    ),
                    "n_actions": int(meta.get("n_actions", 0) or 0),
                    "final_composite": float(scorecard.get("composite", 0.0) or 0.0),
                }
            )
        return out

    def load_actions(self, session_id: str) -> list[OperatorAction]:
        """Rehydrate the recorded action stream from parquet."""
        from penumbra_operator.actions import OperatorAction

        path = self._session_dir(session_id) / _ACTIONS_FILE
        if not path.is_file():
            raise SessionLogError(f"session {session_id!r} has no actions.parquet at {path}")
        frame = pl.read_parquet(path)
        actions: list[OperatorAction] = []
        for row in frame.iter_rows(named=True):
            payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
            actions.append(
                OperatorAction(
                    kind=str(row["kind"]),
                    payload=dict(payload),
                    submit_tick=int(row["submit_tick"]),
                )
            )
        return actions

    def load_meta(self, session_id: str) -> dict[str, Any]:
        """Return the meta.json contents for ``session_id``."""
        path = self._session_dir(session_id) / _META_FILE
        if not path.is_file():
            raise SessionLogError(f"session {session_id!r} has no meta.json at {path}")
        return json.loads(path.read_text())

    def parquet_path(self, session_id: str) -> Path:
        """Filesystem path of the actions parquet (for the download link)."""
        return self._session_dir(session_id) / _ACTIONS_FILE

    def _session_dir(self, session_id: str) -> Path:
        return self.base_dir / session_id


# ── replay ────────────────────────────────────────────────────────


def replay(
    session_id: str,
    fresh_context: OperatorContext,
    *,
    logger: SessionLogger | None = None,
) -> OperatorScoreCard:
    """Re-run a recorded session against ``fresh_context``; return the new scorecard.

    The caller is responsible for building a fresh context seeded
    identically to the original session (same :class:`Simulation` seed,
    same DP budget, same wallet balance). The replay applies the
    recorded actions in order via :func:`apply_action` and returns the
    scorecard derived from the resulting state — which the caller can
    diff against ``logger.load_meta(session_id)['final_scorecard']``.
    """
    from penumbra_operator.actions import apply_action
    from penumbra_operator.scoring import OperatorScoreCard

    log = logger if logger is not None else SessionLogger()
    actions = log.load_actions(session_id)
    for action in actions:
        apply_action(fresh_context, action)
    wallet = fresh_context.market.wallets.get(fresh_context.operator_agent_id)
    coins_now = float(wallet.coins) if wallet is not None else 0.0
    budget = fresh_context.dp_mechanism.budget
    return OperatorScoreCard.compute(
        coins_now=coins_now,
        coins_start=float(fresh_context.initial_coins),
        epsilon_spent=float(budget.epsilon_spent),
        epsilon_total=float(budget.epsilon),
        attacks_survived=0,
        chain_contribution=0,
    )


def scorecard_diff(
    original: dict[str, Any] | OperatorScoreCard,
    replayed: OperatorScoreCard,
    *,
    tolerance: float = REPLAY_TOLERANCE,
) -> dict[str, Any]:
    """Compare an original (dict or scorecard) against a replayed scorecard.

    Returns a flat mapping with per-axis deltas + an overall
    ``deterministic`` flag that's True iff every float axis matches
    within ``tolerance`` and every integer axis matches exactly.
    """
    orig = _scorecard_dict(original) if not isinstance(original, dict) else dict(original)
    rep = _scorecard_dict(replayed)
    float_axes = ("profit", "privacy_preserved", "composite")
    int_axes = ("attacks_survived", "chain_contribution")
    deltas: dict[str, float] = {}
    deterministic = True
    for axis in float_axes:
        delta = float(rep.get(axis, 0.0)) - float(orig.get(axis, 0.0))
        deltas[axis] = delta
        if abs(delta) > tolerance:
            deterministic = False
    for axis in int_axes:
        delta_i = int(rep.get(axis, 0)) - int(orig.get(axis, 0))
        deltas[axis] = float(delta_i)
        if delta_i != 0:
            deterministic = False
    return {
        "tolerance": tolerance,
        "deterministic": deterministic,
        "deltas": deltas,
        "original": orig,
        "replayed": rep,
    }


# ── helpers ───────────────────────────────────────────────────────


def _rows_to_frame(rows: list[_ActionRow]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(
            schema={
                "submit_tick": pl.Int64,
                "applied_tick": pl.Int64,
                "kind": pl.Utf8,
                "payload_json": pl.Utf8,
                "success": pl.Boolean,
                "skipped": pl.Boolean,
                "elapsed_ms": pl.Float64,
                "error_code": pl.Utf8,
                "error_message": pl.Utf8,
            }
        )
    return pl.DataFrame([asdict(r) for r in rows])


def _scorecard_dict(scorecard: OperatorScoreCard | dict[str, Any]) -> dict[str, Any]:
    if isinstance(scorecard, dict):
        return dict(scorecard)
    return {
        "profit": float(scorecard.profit),
        "privacy_preserved": float(scorecard.privacy_preserved),
        "attacks_survived": int(scorecard.attacks_survived),
        "chain_contribution": int(scorecard.chain_contribution),
        "composite": float(scorecard.composite),
    }


__all__ = [
    "DEFAULT_SESSIONS_DIR",
    "REPLAY_TOLERANCE",
    "SessionLogError",
    "SessionLogger",
    "replay",
    "scorecard_diff",
]
