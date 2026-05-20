"""Invariant tests for the procedural arena."""

from __future__ import annotations

import math

import networkx as nx
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from penumbra_core.arena import Arena, ArenaConfig
from penumbra_core.rng import Seeded, bootstrap


@pytest.fixture
def small_arena(seeded: Seeded) -> Arena:
    return Arena.build(ArenaConfig(n_nodes=20, ring_neighbours=4), seeded)


def test_build_yields_connected_graph(small_arena: Arena) -> None:
    assert nx.is_connected(small_arena.graph)


def test_build_assigns_one_cost_per_edge(small_arena: Arena) -> None:
    assert set(small_arena.edge_cost.keys()) == {
        (u, v) if u <= v else (v, u) for u, v in small_arena.graph.edges()
    }


def test_costs_remain_above_floor(small_arena: Arena) -> None:
    small_arena.step_n(500)
    floor = small_arena.config.ou_floor
    assert all(cost >= floor for cost in small_arena.edge_cost.values())


def test_step_preserves_connectivity(small_arena: Arena) -> None:
    """Weather may delete edges but only when the graph stays connected."""
    for _ in range(2_000):
        small_arena.step()
        assert nx.is_connected(small_arena.graph)


def test_goals_migrate(small_arena: Arena) -> None:
    """After many goal-walk periods the goal set should have shifted."""
    initial = list(small_arena.goals)
    small_arena.step_n(small_arena.config.goal_walk_period * 30)
    assert small_arena.goals != initial


def test_reproducibility_across_runs() -> None:
    """Same seed → identical edge costs after the same number of ticks."""
    cfg = ArenaConfig(n_nodes=15)
    a = Arena.build(cfg, bootstrap(123))
    b = Arena.build(cfg, bootstrap(123))
    a.step_n(100)
    b.step_n(100)
    assert a.edge_cost == b.edge_cost
    assert a.goals == b.goals


def test_distinct_seeds_diverge() -> None:
    cfg = ArenaConfig(n_nodes=15)
    a = Arena.build(cfg, bootstrap(123))
    b = Arena.build(cfg, bootstrap(456))
    a.step_n(50)
    b.step_n(50)
    assert a.edge_cost != b.edge_cost


@given(st.integers(min_value=0, max_value=200))
@settings(
    max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
def test_cost_of_edge_is_finite_for_real_edges(small_arena: Arena, ticks: int) -> None:
    small_arena.step_n(ticks)
    for u, v in small_arena.graph.edges():
        assert math.isfinite(small_arena.cost_of(u, v))


def test_cost_of_missing_edge_is_infinite(small_arena: Arena) -> None:
    nodes = list(small_arena.graph.nodes())
    for u in nodes:
        for v in nodes:
            if u != v and not small_arena.graph.has_edge(u, v):
                assert math.isinf(small_arena.cost_of(u, v))
                return  # one missing pair is enough
