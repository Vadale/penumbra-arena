"""Operator save-resume: videogame-style scenario checkpoints.

Concept taught: a *resumable* operator session is two coupled blobs
written together at every meaningful state transition — the
:class:`ScenarioSession` (what the player is doing) and the full
world snapshot (where the simulation, chain, RNG, encrypted buffers
are). On reopen we surface a banner: load both blobs and the player
continues from the saved sim-tick. The clock effectively pauses
while the player is away; failure clauses measured in elapsed
ticks just resume from where they stopped.

Layout
------
    state/operator_sessions/
        active.json          ← banner metadata pointing at the snapshot dir
        <session_id>/
            world/
                chain/...        ← Node.save_to layout
                simulation.pkl   ← save_simulation pickle
            scenario.json    ← scenario_id + start_tick + coins_start + custom

Atomic writes route through :func:`penumbra_core.persistence.atomic_write`
so a crash mid-save leaves the OLD ``active.json`` intact rather than a
half-truncated metadata pointer.

Time semantics: sim-tick based (decided by design). All 12 starter
scenarios use ``elapsed_ticks`` / ``tick`` / ``custom.*`` clauses;
wall-clock predicates are not part of the grammar and would not be
honoured by :func:`penumbra_operator.scenarios._eval_clause`.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from penumbra_core.persistence import atomic_write, load_simulation, save_simulation

from penumbra_operator.scenarios import ScenarioSession

if TYPE_CHECKING:
    from penumbra_chain.node import Node
    from penumbra_core.simulation import Simulation


DEFAULT_SAVE_DIR: Path = Path("state/operator_sessions")
_ACTIVE_FILE = "active.json"
_SCENARIO_FILE = "scenario.json"
_WORLD_SUBDIR = "world"
_CHAIN_SUBDIR = "chain"
_SIM_FILE = "simulation.pkl"


class SaveResumeError(Exception):
    """Raised when the active save is missing, malformed, or references vanished data."""


@dataclass(frozen=True, slots=True)
class ActiveSave:
    """Pointer record persisted at ``state/operator_sessions/active.json``."""

    session_id: str
    scenario_id: str
    scenario_label: str
    saved_at_tick: int
    saved_at_wall_iso: str
    world_snapshot_path: str


def save_root(directory: Path | None = None) -> Path:
    """Return the configured save root (creates parents on first write)."""
    return Path(directory) if directory is not None else DEFAULT_SAVE_DIR


def active_pointer_path(directory: Path | None = None) -> Path:
    """Where the banner metadata lives."""
    return save_root(directory) / _ACTIVE_FILE


def session_dir(session_id: str, directory: Path | None = None) -> Path:
    """Where one session's world + scenario blobs live."""
    return save_root(directory) / session_id


def world_dir_for(session_id: str, directory: Path | None = None) -> Path:
    """Subdirectory holding chain + simulation.pkl for one session."""
    return session_dir(session_id, directory) / _WORLD_SUBDIR


def _serialise_session(session: ScenarioSession) -> dict[str, Any]:
    return {
        "scenario_id": session.scenario_id,
        "start_tick": int(session.start_tick),
        "coins_start": float(session.coins_start),
        "custom": {str(k): float(v) for k, v in session.custom.items()},
    }


def _deserialise_session(payload: dict[str, Any]) -> ScenarioSession:
    custom_raw = payload.get("custom") or {}
    if not isinstance(custom_raw, dict):
        raise SaveResumeError("scenario.json: 'custom' must be an object")
    return ScenarioSession(
        scenario_id=str(payload["scenario_id"]),
        start_tick=int(payload["start_tick"]),
        coins_start=float(payload["coins_start"]),
        custom={str(k): float(v) for k, v in custom_raw.items()},
    )


def save_session(
    *,
    session_id: str,
    scenario_id: str,
    scenario_label: str,
    scenario_session: ScenarioSession,
    simulation: Simulation,
    node: Node,
    directory: Path | None = None,
) -> ActiveSave:
    """Snapshot the world + the live ScenarioSession, then rewrite ``active.json``.

    Ordering: world (chain + simulation.pkl) → scenario.json → active.json.
    Each individual write is atomic via tmp + ``os.replace``. The
    pointer rewrite lands last so readers either see the OLD pointer
    (and an intact old snapshot) or the NEW pointer (and the just-
    written snapshot) — never the new pointer paired with a partial
    snapshot.
    """
    root = save_root(directory)
    root.mkdir(parents=True, exist_ok=True)
    target = session_dir(session_id, directory)
    target.mkdir(parents=True, exist_ok=True)

    world = world_dir_for(session_id, directory)
    world.mkdir(parents=True, exist_ok=True)
    node.save_to(world / _CHAIN_SUBDIR)
    save_simulation(simulation, world / _SIM_FILE)

    scenario_blob = json.dumps(
        _serialise_session(scenario_session), indent=2, sort_keys=True
    ).encode("utf-8")
    atomic_write(target / _SCENARIO_FILE, scenario_blob)

    saved_at_wall_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    pointer = ActiveSave(
        session_id=session_id,
        scenario_id=scenario_id,
        scenario_label=scenario_label,
        saved_at_tick=int(simulation.tick_counter),
        saved_at_wall_iso=saved_at_wall_iso,
        world_snapshot_path=str(world),
    )
    atomic_write(
        active_pointer_path(directory),
        json.dumps(
            {
                "session_id": pointer.session_id,
                "scenario_id": pointer.scenario_id,
                "scenario_label": pointer.scenario_label,
                "saved_at_tick": pointer.saved_at_tick,
                "saved_at_wall_iso": pointer.saved_at_wall_iso,
                "world_snapshot_path": pointer.world_snapshot_path,
            },
            indent=2,
            sort_keys=True,
        ).encode("utf-8"),
    )
    return pointer


def load_active(directory: Path | None = None) -> ActiveSave | None:
    """Read ``active.json`` if present; return None for no-resumable-session."""
    path = active_pointer_path(directory)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SaveResumeError(f"failed to read {path}: {exc}") from exc
    try:
        return ActiveSave(
            session_id=str(payload["session_id"]),
            scenario_id=str(payload["scenario_id"]),
            scenario_label=str(payload.get("scenario_label", "")),
            saved_at_tick=int(payload["saved_at_tick"]),
            saved_at_wall_iso=str(payload.get("saved_at_wall_iso", "")),
            world_snapshot_path=str(payload["world_snapshot_path"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise SaveResumeError(f"malformed active.json at {path}: {exc}") from exc


def load_scenario_session(session_id: str, directory: Path | None = None) -> ScenarioSession:
    """Reverse :func:`save_session` for the scenario half (cheap, no world load)."""
    path = session_dir(session_id, directory) / _SCENARIO_FILE
    if not path.is_file():
        raise SaveResumeError(f"no scenario.json under {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SaveResumeError(f"failed to read {path}: {exc}") from exc
    return _deserialise_session(payload)


def load_world_for_session(
    session_id: str, directory: Path | None = None
) -> tuple[Node, Simulation]:
    """Reload the chain Node + Simulation snapshotted under ``session_id``."""
    from penumbra_chain.node import Node as _Node

    world = world_dir_for(session_id, directory)
    chain = world / _CHAIN_SUBDIR
    sim_pkl = world / _SIM_FILE
    if not chain.is_dir():
        raise SaveResumeError(f"missing chain snapshot at {chain}")
    if not sim_pkl.is_file():
        raise SaveResumeError(f"missing simulation snapshot at {sim_pkl}")
    node = _Node.restore_from(chain)
    simulation = load_simulation(sim_pkl)
    return node, simulation


def discard_active(
    directory: Path | None = None,
    *,
    session_id: str | None = None,
    drop_snapshot_dir: bool = False,
) -> dict[str, Any]:
    """Delete ``active.json``; optionally wipe one session's snapshot dir too.

    Default policy: keep the per-session snapshot dir so a future replay
    feature can browse historical saves. Pass ``drop_snapshot_dir=True``
    + ``session_id`` for an explicit "burn it all" semantics (the
    abandon-scenario path uses this once we're sure the player walked
    away on purpose).
    """
    removed_pointer = False
    removed_dir = False
    pointer = active_pointer_path(directory)
    if pointer.is_file():
        pointer.unlink()
        removed_pointer = True
    if drop_snapshot_dir and session_id is not None:
        target = session_dir(session_id, directory)
        if target.is_dir():
            shutil.rmtree(target)
            removed_dir = True
    return {"removed_pointer": removed_pointer, "removed_dir": removed_dir}


def discard_session_dir(session_id: str, directory: Path | None = None) -> bool:
    """Recursively delete the session snapshot dir under save_root. Returns True iff removed."""
    target = session_dir(session_id, directory)
    if target.is_dir():
        shutil.rmtree(target)
        return True
    return False


__all__ = [
    "DEFAULT_SAVE_DIR",
    "ActiveSave",
    "SaveResumeError",
    "active_pointer_path",
    "discard_active",
    "discard_session_dir",
    "load_active",
    "load_scenario_session",
    "load_world_for_session",
    "save_root",
    "save_session",
    "session_dir",
    "world_dir_for",
]
