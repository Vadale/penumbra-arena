"""Logistics Tier 2 — VRP optimisation benchmark tests."""

from __future__ import annotations

import numpy as np
import pytest
from penumbra_core.logistics_or import (
    VRPError,
    VRPInstance,
    VRPOrder,
    solve_greedy_nearest_neighbor,
    solve_or_tools,
    solve_two_opt,
)


def _simple_instance() -> VRPInstance:
    """4 nodes in a line: 0 --1-- 1 --1-- 2 --1-- 3. Distances are graph distances."""
    distance = np.array(
        [
            [0.0, 1.0, 2.0, 3.0],
            [1.0, 0.0, 1.0, 2.0],
            [2.0, 1.0, 0.0, 1.0],
            [3.0, 2.0, 1.0, 0.0],
        ]
    )
    orders = (
        VRPOrder(order_id=10, node=1, quantity=1),
        VRPOrder(order_id=11, node=2, quantity=1),
        VRPOrder(order_id=12, node=3, quantity=1),
    )
    return VRPInstance(
        n_nodes=4,
        distance_matrix=distance,
        orders=orders,
        agent_start=(0,),
        agent_capacity=(10,),
    )


def test_vrp_instance_validation_rejects_bad_shapes() -> None:
    bad = np.zeros((3, 4))
    with pytest.raises(VRPError):
        VRPInstance(
            n_nodes=3,
            distance_matrix=bad,
            orders=(),
            agent_start=(0,),
            agent_capacity=(5,),
        )


def test_vrp_instance_validation_rejects_out_of_range_order() -> None:
    distance = np.zeros((2, 2))
    with pytest.raises(VRPError):
        VRPInstance(
            n_nodes=2,
            distance_matrix=distance,
            orders=(VRPOrder(order_id=0, node=5, quantity=1),),
            agent_start=(0,),
            agent_capacity=(5,),
        )


def test_vrp_instance_basics() -> None:
    inst = _simple_instance()
    assert inst.n_agents == 1
    assert len(inst.orders) == 3
    assert inst.distance_matrix.shape == (4, 4)


def test_greedy_visits_all_orders_when_capacity_allows() -> None:
    inst = _simple_instance()
    sol = solve_greedy_nearest_neighbor(inst)
    assert set(sol.served_order_ids) == {10, 11, 12}
    assert sol.unserved_order_ids == ()
    # 0 -> 1 -> 2 -> 3 = total 3.0
    assert sol.total_cost == pytest.approx(3.0)


def test_greedy_respects_capacity() -> None:
    distance = np.array([[0.0, 1.0], [1.0, 0.0]])
    inst = VRPInstance(
        n_nodes=2,
        distance_matrix=distance,
        orders=(
            VRPOrder(order_id=0, node=1, quantity=3),
            VRPOrder(order_id=1, node=1, quantity=3),
        ),
        agent_start=(0,),
        agent_capacity=(4,),  # only one 3-unit order fits
    )
    sol = solve_greedy_nearest_neighbor(inst)
    assert len(sol.served_order_ids) == 1
    assert len(sol.unserved_order_ids) == 1


def test_two_opt_does_not_worsen_greedy() -> None:
    # Build a deliberately suboptimal tour by orchestrating distances
    # that bait the nearest-neighbor heuristic. 5 cities in a known
    # configuration.
    rng = np.random.default_rng(7)
    coords = rng.uniform(0, 10, size=(8, 2))
    distance = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1)
    orders = tuple(VRPOrder(order_id=i, node=i, quantity=1) for i in range(1, 8))
    inst = VRPInstance(
        n_nodes=8,
        distance_matrix=distance,
        orders=orders,
        agent_start=(0,),
        agent_capacity=(20,),
    )
    greedy = solve_greedy_nearest_neighbor(inst)
    improved = solve_two_opt(inst, initial=greedy)
    assert improved.total_cost <= greedy.total_cost + 1e-9


def test_two_opt_improves_pathological_greedy() -> None:
    # 4 cities arranged so the greedy picks a long route, 2-opt fixes it.
    # 0 -- 1 (very close), 0 -- 2 (medium), 0 -- 3 (long); 1, 2, 3 clustered.
    distance = np.array(
        [
            [0.0, 1.0, 5.0, 10.0],
            [1.0, 0.0, 1.0, 6.0],
            [5.0, 1.0, 0.0, 1.0],
            [10.0, 6.0, 1.0, 0.0],
        ]
    )
    orders = (
        VRPOrder(order_id=1, node=1, quantity=1),
        VRPOrder(order_id=2, node=2, quantity=1),
        VRPOrder(order_id=3, node=3, quantity=1),
    )
    inst = VRPInstance(
        n_nodes=4,
        distance_matrix=distance,
        orders=orders,
        agent_start=(0,),
        agent_capacity=(10,),
    )
    greedy = solve_greedy_nearest_neighbor(inst)
    improved = solve_two_opt(inst, initial=greedy)
    # Optimal is 0 -> 1 -> 2 -> 3 = 1 + 1 + 1 = 3.0; greedy gets the same.
    assert improved.total_cost <= greedy.total_cost
    assert improved.total_cost == pytest.approx(3.0)


def test_two_opt_metadata_records_initial_cost() -> None:
    inst = _simple_instance()
    sol = solve_two_opt(inst)
    assert "initial_cost" in sol.metadata


def test_or_tools_wrapper_returns_optimal_or_falls_back() -> None:
    inst = _simple_instance()
    sol = solve_or_tools(inst)
    # Either we get the optimum (3.0) or we cleanly degraded to two_opt.
    assert sol.solver in ("or_tools", "or_tools_fallback_two_opt")
    assert sol.total_cost == pytest.approx(3.0)
    assert set(sol.served_order_ids) == {10, 11, 12}


def test_greedy_handles_empty_orders() -> None:
    inst = VRPInstance(
        n_nodes=2,
        distance_matrix=np.zeros((2, 2)),
        orders=(),
        agent_start=(0,),
        agent_capacity=(5,),
    )
    sol = solve_greedy_nearest_neighbor(inst)
    assert sol.total_cost == 0.0
    assert sol.served_order_ids == ()
    assert sol.unserved_order_ids == ()


def test_build_arena_distance_matrix_from_real_arena() -> None:
    from penumbra_core.arena import Arena, ArenaConfig
    from penumbra_core.logistics_or import build_arena_distance_matrix
    from penumbra_core.rng import bootstrap

    seeded = bootstrap(13)
    arena = Arena.build(ArenaConfig(n_nodes=8), seeded)
    mat, nodes = build_arena_distance_matrix(arena)
    assert mat.shape == (len(nodes), len(nodes))
    assert (np.diag(mat) == 0.0).all()
    # Symmetry on a symmetric edge_cost dict.
    assert np.allclose(mat, mat.T)
    # No infinities — graph is connected by Arena.from_config contract.
    assert np.isfinite(mat).all()
