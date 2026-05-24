"""Tests for the Phase 5 Tier 4 in-memory branch registry."""

from __future__ import annotations

import pytest
from penumbra_core.agent import random_walk_policy
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_transport.world import (
    DEFAULT_POLICY_REGISTRY,
    BranchNotFoundError,
    InvalidSnapshotNameError,
    WorldBranchRegistry,
    register_branch_policy,
)


def _fresh_sim() -> Simulation:
    return Simulation.build(SimulationConfig(n_agents=4, match_max_ticks=50), bootstrap(seed=7))


def test_branch_creates_n_clones() -> None:
    reg = WorldBranchRegistry()
    sim = _fresh_sim()
    ids = reg.branch("exp", sim, n_branches=3)
    assert ids == ["exp-1", "exp-2", "exp-3"]
    listed = reg.list_branches()
    assert len(listed) == 3
    assert all(b["parent_tick"] == sim.tick_counter for b in listed)


def test_branches_advance_independently() -> None:
    reg = WorldBranchRegistry()
    sim = _fresh_sim()
    ids = reg.branch("indep", sim, n_branches=2)
    reg.advance(ids[0], ticks=3)
    listed = {b["branch_id"]: b for b in reg.list_branches()}
    a_tick = int(listed[ids[0]]["current_tick"])  # type: ignore[arg-type]
    b_tick = int(listed[ids[1]]["current_tick"])  # type: ignore[arg-type]
    assert a_tick >= b_tick


def test_compare_returns_per_branch_rows() -> None:
    reg = WorldBranchRegistry()
    sim = _fresh_sim()
    ids = reg.branch("cmp", sim, n_branches=2)
    reg.advance(ids[0], ticks=2)
    payload = reg.compare(ids)
    rows = payload["branches"]
    assert isinstance(rows, list)
    assert len(rows) == 2
    assert {r["branch_id"] for r in rows} == set(ids)
    for r in rows:
        assert len(r["positions"]) == r["n_agents"]
        assert len(r["wealth"]) == r["n_agents"]


def test_unknown_branch_raises() -> None:
    reg = WorldBranchRegistry()
    with pytest.raises(BranchNotFoundError):
        reg.advance("does-not-exist", ticks=1)
    with pytest.raises(BranchNotFoundError):
        reg.compare(["nope"])


def test_drop_removes_branch() -> None:
    reg = WorldBranchRegistry()
    sim = _fresh_sim()
    ids = reg.branch("drop", sim, n_branches=1)
    assert reg.drop(ids[0]) is True
    assert reg.drop(ids[0]) is False


def test_branch_rejects_bad_name() -> None:
    reg = WorldBranchRegistry()
    sim = _fresh_sim()
    with pytest.raises(InvalidSnapshotNameError):
        reg.branch("bad/name", sim, n_branches=1)
    with pytest.raises(InvalidSnapshotNameError):
        reg.branch("good", sim, n_branches=0)


def test_branched_agents_preserve_random_walk_policy_and_tick() -> None:
    """Branched random-walk agents reattach a callable policy and advance cleanly."""
    reg = WorldBranchRegistry()
    sim = _fresh_sim()
    # Sanity: source agents are running random_walk_policy by default.
    assert all(a.policy is random_walk_policy for a in sim.agents)
    ids = reg.branch("preserve", sim, n_branches=2)

    for bid in ids:
        entry = reg.branches[bid]
        assert all(a.policy is not None for a in entry.simulation.agents)
        # Each reattached policy is the actual random_walk_policy from
        # the default registry — not a stand-in lambda.
        assert all(a.policy is random_walk_policy for a in entry.simulation.agents)
        assert all(callable(a.policy) for a in entry.simulation.agents)
        # And the branch ticks without exploding.
        for _ in range(5):
            entry.simulation.tick()
        assert entry.simulation.tick_counter >= 5


def test_register_branch_policy_round_trip() -> None:
    """A runtime-registered policy is reattached on branch."""

    def custom_policy(obs, rng):  # type: ignore[no-untyped-def]
        del rng
        return obs.position

    register_branch_policy("custom_policy", custom_policy)
    try:
        reg = WorldBranchRegistry()
        sim = _fresh_sim()
        for a in sim.agents:
            a.policy = custom_policy  # type: ignore[assignment]
        ids = reg.branch("reg", sim, n_branches=1)
        entry = reg.branches[ids[0]]
        assert all(a.policy is custom_policy for a in entry.simulation.agents)
        # Tick still works.
        entry.simulation.tick()
    finally:
        DEFAULT_POLICY_REGISTRY.pop("custom_policy", None)
