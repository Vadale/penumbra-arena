"""Simulation snapshot / restore.

Concept taught: complete a simulation's *resumable* state is more than
"current agent positions". We capture:
- the SimulationConfig (so we can rebuild the arena dimensions),
- the master seed + numpy bit-generator state (so the RNG resumes
  exactly where it left off),
- the arena: graph topology + per-edge OU cost state + goal positions
  + arena tick counter,
- per-agent: position, home, distance_travelled,
- the current Match's id + status + started_tick + winner data,
- the simulation tick_counter and next_match_id.

Two things are deliberately *not* captured:
- Agent.policy — functions and closures don't pickle cleanly across
  versions, especially closures over torch models. On restore the
  caller supplies a fresh policy_factory.
- on_match_end callback — wired by whoever owns the simulation.

We persist as a pickled dict for fidelity. NetworkX graphs are pickle-
friendly out of the box. Files end up at
`state/snapshots/<name>/simulation.pkl`.

Shared atomic-write helper: :func:`atomic_write` mirrors the
``_atomic_owner_only_write`` idiom from
``penumbra_chain.persistence`` (tmp file + fsync + os.replace), but
defaults to mode ``0o644`` so non-secret operator-save payloads
(session metadata, world snapshots) re-use the crash-safe primitive
without forcing owner-only perms across the codebase. Secret-bearing
chain writes keep their bespoke ``0o600`` helper.
"""

from __future__ import annotations

import os
import pickle
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from penumbra_core.agent import Agent, AgentObservation
from penumbra_core.arena import Arena, NodeId
from penumbra_core.match import Match
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig


def atomic_write(path: Path, data: bytes, *, mode: int = 0o644) -> None:
    """Crash-safe write: tmp + fsync + ``os.replace`` onto ``path``.

    Shared utility re-used by the operator save-resume layer (and any
    other caller that needs a torn-write-free dump). Defaults to
    ``0o644``; pass ``mode=0o600`` for secret material to match the
    chain's per-validator-secrets helper.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(str(tmp), flags, mode)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))


def save_simulation(sim: Simulation, path: Path) -> None:
    """Persist the simulation to `path` (a single .pkl file).

    `path.parent` must exist. We dump a plain dict so the schema is
    visible without re-importing the Penumbra types — useful for
    forensic inspection via `pickletools`.
    """
    state: dict[str, Any] = {
        "schema_version": 1,
        "config": asdict(sim.config),
        "seeded": {
            "master": sim.seeded.master,
            "streams": dict(sim.seeded.streams),
            "numpy_bg_state": sim.seeded.numpy.bit_generator.state,
        },
        "arena": sim.arena,  # NetworkX graph pickles fine
        "agents": [
            {
                "id": a.id,
                "position": a.position,
                "home": a.home,
                "distance_travelled": a.distance_travelled,
                "last_action_tick": a.last_action_tick,
                "metadata": dict(a.metadata),
            }
            for a in sim.agents
        ],
        "current_match": sim.current_match,
        "next_match_id": sim.next_match_id,
        "tick_counter": sim.tick_counter,
        "state": sim.state.value,
    }
    atomic_write(path, pickle.dumps(state))


def load_simulation(
    path: Path,
    *,
    policy_factory: Callable[[int], Callable[[AgentObservation, np.random.Generator], NodeId]]
    | None = None,
) -> Simulation:
    """Reverse `save_simulation`. Reattaches policies via `policy_factory`.

    If `policy_factory` is None we use the random-walk baseline so
    something runs; in production hand in the same factory the live
    Simulation was using (e.g. mappo_policy_factory).
    """
    if not path.is_file():
        raise FileNotFoundError(f"simulation snapshot not found: {path}")
    payload: dict[str, Any] = pickle.loads(path.read_bytes())  # noqa: S301
    if payload.get("schema_version") != 1:
        raise ValueError(f"unknown snapshot schema_version={payload.get('schema_version')!r}")

    # Reconstruct config + Seeded.
    cfg_payload = payload["config"]
    # arena cfg comes back as a dict; rebuild it as ArenaConfig.
    from penumbra_core.arena import ArenaConfig

    arena_cfg = ArenaConfig(**cfg_payload.pop("arena"))
    config = SimulationConfig(arena=arena_cfg, **cfg_payload)

    # Re-bootstrap then restore the bit-generator state — this gives us
    # a fully-seeded Seeded with the numpy stream resumed exactly.
    seeded = bootstrap(payload["seeded"]["master"])
    seeded.numpy.bit_generator.state = payload["seeded"]["numpy_bg_state"]
    for domain, subkey in payload["seeded"]["streams"].items():
        # Replay the sub-key cache. We can't easily restore each domain
        # generator's bit-state, but the sub-keys themselves are stable
        # so any new numpy_for(domain) call returns the same Generator
        # state it would have at this moment in a fresh seeded run.
        seeded.streams[domain] = subkey

    arena: Arena = payload["arena"]

    # Reattach policies.
    if policy_factory is None:
        from penumbra_core.agent import random_walk_policy

        def _default_factory(
            _agent_id: int,
        ) -> Callable[[AgentObservation, np.random.Generator], NodeId]:
            return random_walk_policy

        policy_factory = _default_factory

    agents = [
        Agent(
            id=row["id"],
            position=row["position"],
            home=row["home"],
            distance_travelled=row["distance_travelled"],
            last_action_tick=row.get("last_action_tick", -1),
            metadata=dict(row.get("metadata", {})),
            policy=policy_factory(row["id"]),
        )
        for row in payload["agents"]
    ]

    current_match: Match = payload["current_match"]

    from penumbra_core.simulation import RunState

    return Simulation(
        config=config,
        seeded=seeded,
        arena=arena,
        agents=agents,
        current_match=current_match,
        next_match_id=payload["next_match_id"],
        tick_counter=payload["tick_counter"],
        state=RunState(payload["state"]),
    )
