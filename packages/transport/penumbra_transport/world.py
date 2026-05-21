"""World snapshots: save + load + list named simulation+chain checkpoints.

Concept taught: a "world" snapshot is the FULL state of the running
system — chain + simulation — persisted to disk under a human-
friendly name, restorable across process restarts. Both layers are
captured so a snapshot represents one moment in time you can return
to.

Layout
------
    state/snapshots/<name>/
        chain/
            validators.json
            secrets.json
            state.json
            blocks.parquet
            mempool.parquet
            pending_slashings.json
        simulation.pkl    ← arena + agents + RNG state

Defaults to `state/snapshots/` under the project root; configurable
via `PENUMBRA_SNAPSHOTS_DIR`.

Hot-swap policy
---------------
- `/world/save` snapshots the LIVE chain + simulation.
- `/world/load` hot-swaps the chain into the running orchestrator
  (the chain has no in-flight state). The simulation snapshot is
  saved alongside but is NOT auto-loaded into the running process —
  loading it requires a process restart with
  `PENUMBRA_SIM_SNAPSHOT=<path>` so the lifespan picks it up.
  Rationale: hot-swapping a running simulation under an active tick
  loop is complex and error-prone; restart is the safe path.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from penumbra_chain.node import Node
from penumbra_core.persistence import load_simulation, save_simulation
from penumbra_core.simulation import Simulation

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def snapshots_root() -> Path:
    """Where to store snapshots. Override with PENUMBRA_SNAPSHOTS_DIR."""
    override = os.environ.get("PENUMBRA_SNAPSHOTS_DIR")
    if override:
        return Path(override)
    return Path.cwd() / "state" / "snapshots"


def _validate_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise InvalidSnapshotNameError(f"snapshot name {name!r} must match {_NAME_RE.pattern}")


def save_world(name: str, node: Node, simulation: Simulation | None = None) -> Path:
    """Snapshot the chain (and optionally the simulation) to state/snapshots/<name>/.

    Returns the world directory (parent of the chain dir).
    """
    _validate_name(name)
    world = snapshots_root() / name
    world.mkdir(parents=True, exist_ok=True)
    chain_target = world / "chain"
    node.save_to(chain_target)
    if simulation is not None:
        save_simulation(simulation, world / "simulation.pkl")
    return world


def load_world(name: str) -> Node:
    """Load chain from state/snapshots/<name>/chain/.

    Companion `simulation.pkl` (if present) is left on disk; callers
    can read it via `load_world_simulation(name, policy_factory)`.
    """
    _validate_name(name)
    target = snapshots_root() / name / "chain"
    if not target.is_dir():
        raise SnapshotNotFoundError(f"no snapshot at {target}")
    return Node.restore_from(target)


def load_world_simulation(
    name: str,
    *,
    policy_factory: Callable[[int], Any] | None = None,
) -> Simulation:
    """Load the simulation half of a world snapshot.

    `policy_factory(agent_id) -> Policy` is the same callable the
    runtime uses (e.g. mappo_policy_factory). If None, restored
    agents use random_walk_policy.
    """
    _validate_name(name)
    sim_path = snapshots_root() / name / "simulation.pkl"
    if not sim_path.is_file():
        raise SnapshotNotFoundError(f"no simulation snapshot at {sim_path}")
    return load_simulation(sim_path, policy_factory=policy_factory)


@dataclass(frozen=True, slots=True)
class SnapshotEntry:
    """One snapshot's metadata for `/world/list`."""

    name: str
    path: str
    chain_height: int
    has_secrets: bool
    has_simulation: bool


def list_worlds() -> list[SnapshotEntry]:
    """Enumerate every directory under state/snapshots/<name>/."""
    root = snapshots_root()
    if not root.is_dir():
        return []
    out: list[SnapshotEntry] = []
    for name_dir in sorted(root.iterdir()):
        chain_dir = name_dir / "chain"
        if not chain_dir.is_dir():
            continue
        blocks_path = chain_dir / "blocks.parquet"
        height = 0
        state_path = chain_dir / "state.json"
        if state_path.is_file():
            import json

            try:
                state = json.loads(state_path.read_text())
                height = int(state.get("height", 0))
            except (OSError, ValueError):
                height = 0
        out.append(
            SnapshotEntry(
                name=name_dir.name,
                path=str(chain_dir),
                chain_height=height,
                has_secrets=(chain_dir / "secrets.json").is_file() or blocks_path.is_file(),
                has_simulation=(name_dir / "simulation.pkl").is_file(),
            )
        )
    return out


class InvalidSnapshotNameError(ValueError):
    """Raised when the requested snapshot name violates the safe-chars regex."""


class SnapshotNotFoundError(FileNotFoundError):
    """Raised when load_world() can't find the requested snapshot."""
