"""World snapshots: save + load + list named simulation+chain checkpoints + in-memory branches.

Concept taught: a "world" snapshot is the FULL state of the running
system — chain + simulation — persisted to disk under a human-
friendly name, restorable across process restarts. Both layers are
captured so a snapshot represents one moment in time you can return
to. The Phase 5 Tier 4 extension adds *branches*: N pickle-clones of
the live simulation that can be advanced independently and compared
side-by-side. Branches live in process memory, not on disk, so they
are cheap to spawn and disappear on restart by design.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from numpy.random import Generator as NumpyGenerator
from penumbra_chain.node import Node
from penumbra_core.agent import AgentObservation, Policy, random_walk_policy
from penumbra_core.arena import NodeId
from penumbra_core.persistence import load_simulation, save_simulation
from penumbra_core.simulation import Simulation
from penumbra_crypto.crypto_persistence import (
    save_ckks_context,
    save_dp_budget,
)
from penumbra_crypto.dp import PrivacyBudget


def _greedy_nearest_goal_policy(observation: AgentObservation, rng: NumpyGenerator) -> NodeId:
    """Deterministic baseline: step onto the cheapest visible-goal neighbour.

    Falls through to picking the lowest-cost neighbour by id-tie-break
    when no neighbour is a goal. Pure + pickleable so branched
    simulations can reattach it after a clone.
    """
    del rng
    neighbours = observation.neighbour_costs
    if not neighbours:
        return observation.position
    goals = set(observation.visible_goals)
    candidates = [n for n in neighbours if n in goals]
    if candidates:
        return min(candidates, key=lambda n: (neighbours[n], n))
    return min(neighbours.keys(), key=lambda n: (neighbours[n], n))


# Registry of default policy factories the branch reattacher can
# reach by name. Custom-injected policies (e.g. closures over the live
# orchestrator, sandbox-uploaded code) are NOT preserved across branch
# by design — the registry only covers the stable defaults.
DEFAULT_POLICY_REGISTRY: dict[str, Policy] = {
    "random_walk_policy": random_walk_policy,
    "greedy_nearest_goal_policy": _greedy_nearest_goal_policy,
}


def register_branch_policy(name: str, policy: Policy) -> None:
    """Expose a policy to the branch reattacher under ``name``.

    Wired up by the runtime when it loads, e.g., the MAPPO actor:

        register_branch_policy("mappo_policy", mappo_policy_singleton)

    so that branching a sim whose agents ran MAPPO reattaches the same
    callable instead of falling back to random walk.
    """
    if not name:
        raise InvalidSnapshotNameError("policy name must be non-empty")
    DEFAULT_POLICY_REGISTRY[name] = policy


def _policy_tag(policy: Policy) -> str:
    """Stable identifier for a Policy: prefer __name__ then qualname."""
    name = getattr(policy, "__name__", None)
    if name:
        return str(name)
    return getattr(policy, "__qualname__", repr(policy))


def _reattach_policy(tag: str) -> Policy:
    """Look ``tag`` up in the registry; fall back to random walk."""
    return DEFAULT_POLICY_REGISTRY.get(tag, random_walk_policy)


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


def save_world(
    name: str,
    node: Node,
    simulation: Simulation | None = None,
    *,
    ckks_backend: object | None = None,
    dp_budget: PrivacyBudget | None = None,
) -> Path:
    """Snapshot the chain (and optionally simulation + CKKS + DP budget).

    Returns the world directory (parent of the chain dir).
    """
    _validate_name(name)
    world = snapshots_root() / name
    world.mkdir(parents=True, exist_ok=True)
    chain_target = world / "chain"
    node.save_to(chain_target)
    if simulation is not None:
        save_simulation(simulation, world / "simulation.pkl")
    if ckks_backend is not None:
        save_ckks_context(ckks_backend, world / "crypto" / "ckks_context.bin")
    if dp_budget is not None:
        save_dp_budget(dp_budget, world / "crypto" / "dp_budget.json")
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


class BranchNotFoundError(KeyError):
    """Raised when a branch id is unknown to the registry."""


@dataclass(slots=True)
class BranchEntry:
    """One in-memory branched simulation."""

    branch_id: str
    parent_tick: int
    simulation: Simulation


@dataclass(slots=True)
class WorldBranchRegistry:
    """Process-local map of branch_id → cloned Simulation.

    Cloning is done via `pickle.dumps`/`loads` which round-trips agents,
    arena, RNG, and policies. Branches stay in memory; they are not
    persisted across restarts on purpose — branching is a "what if?"
    tool, not a checkpoint mechanism.
    """

    branches: dict[str, BranchEntry] = field(default_factory=dict)

    def branch(self, name: str, source: Simulation, *, n_branches: int = 5) -> list[str]:
        """Snapshot `source` into `n_branches` independent clones.

        Returns the list of newly-minted branch ids. Each id is the
        prefix `name` plus a 1-based index so they sort lexically.

        Policy preservation
        -------------------
        Cloning routes through `save_simulation` / `load_simulation`,
        which strips agent policies + match-end callbacks (closures
        over the live orchestrator never pickle cleanly). Before
        cloning we RECORD each agent's policy tag (its `__name__`),
        then after restoring we look the tag up in
        `DEFAULT_POLICY_REGISTRY` and reattach. The default registry
        ships `random_walk_policy` + `greedy_nearest_goal_policy`;
        runtimes register `mappo_policy` (and any other in-house
        defaults) at startup via `register_branch_policy`.

        Custom policies injected by the sandbox / REPL are NOT
        preserved — the registry only covers stable defaults. Agents
        whose policy tag is unknown fall back to `random_walk_policy`
        so the branch still ticks.
        """
        _validate_name(name)
        if n_branches < 1:
            raise InvalidSnapshotNameError("n_branches must be >= 1")
        import tempfile

        policy_tags: list[str] = [_policy_tag(a.policy) for a in source.agents]

        def _factory(agent_id: int) -> Policy:
            if 0 <= agent_id < len(policy_tags):
                return _reattach_policy(policy_tags[agent_id])
            return random_walk_policy

        created: list[str] = []
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=True) as fp:
            save_simulation(source, Path(fp.name))
            for i in range(1, n_branches + 1):
                branch_id = f"{name}-{i}"
                clone = load_simulation(Path(fp.name), policy_factory=_factory)
                self.branches[branch_id] = BranchEntry(
                    branch_id=branch_id, parent_tick=source.tick_counter, simulation=clone
                )
                created.append(branch_id)
        return created

    def advance(self, branch_id: str, ticks: int) -> dict[str, str | int]:
        """Advance the named branch by up to `ticks` ticks; returns final tick."""
        entry = self.branches.get(branch_id)
        if entry is None:
            raise BranchNotFoundError(f"no branch {branch_id!r}")
        for _ in range(max(0, ticks)):
            entry.simulation.tick()
        return {
            "branch_id": branch_id,
            "parent_tick": entry.parent_tick,
            "current_tick": entry.simulation.tick_counter,
        }

    def list_branches(self) -> list[dict[str, object]]:
        """Snapshot of every branch for /world/branches."""
        return [
            {
                "branch_id": b.branch_id,
                "parent_tick": b.parent_tick,
                "current_tick": b.simulation.tick_counter,
                "n_agents": len(b.simulation.agents),
            }
            for b in self.branches.values()
        ]

    def compare(self, branch_ids: list[str]) -> dict[str, object]:
        """Side-by-side diff: positions + wealth + tick counter per branch."""
        rows: list[dict[str, object]] = []
        for bid in branch_ids:
            entry = self.branches.get(bid)
            if entry is None:
                raise BranchNotFoundError(f"no branch {bid!r}")
            sim = entry.simulation
            positions = [int(a.position) for a in sim.agents]
            wealth = [float(getattr(a, "coins", 0.0)) for a in sim.agents]
            rows.append(
                {
                    "branch_id": bid,
                    "current_tick": sim.tick_counter,
                    "positions": positions,
                    "wealth": wealth,
                    "n_agents": len(sim.agents),
                }
            )
        return {"branches": rows}

    def drop(self, branch_id: str) -> bool:
        """Forget the named branch; returns True iff it existed."""
        return self.branches.pop(branch_id, None) is not None


_GLOBAL_BRANCHES = WorldBranchRegistry()


def global_branches() -> WorldBranchRegistry:
    """Process-wide branch registry used by the FastAPI endpoints."""
    return _GLOBAL_BRANCHES
