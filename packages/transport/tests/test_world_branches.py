"""Tests for the Phase 5 Tier 4 in-memory branch registry."""

from __future__ import annotations

import pytest
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_transport.world import (
    BranchNotFoundError,
    InvalidSnapshotNameError,
    WorldBranchRegistry,
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
