"""OR-style vehicle-routing solver as a centralized-planner benchmark.

Concept taught: a Vehicle Routing Problem (VRP) solver knows EVERYTHING
— all pending orders, all distances, all cargo capacities. A learned
MAPPO policy (or the in-house heuristic) makes DECENTRALIZED decisions
with only local observation. The cost gap measures how much we lose
to decentralization; the absolute total cost measures how good our
heuristic / learned policy is on its own.

Spec: LOGISTICS_PLAN.md Tier 2.

This module is pure Python + numpy + (optional) OR-Tools. It NEVER
mutates orchestrator / market state — `compute_vrp_baseline` only reads
the live state and returns a `VRPSolution`. Three solver strategies:

  1. `solve_greedy_nearest_neighbor` — fast O(N^2) heuristic. Each
     vehicle, starting at its current node, repeatedly visits the
     cheapest reachable open order it can still carry.
  2. `solve_two_opt` — local-search improver on top of greedy. Walks
     each vehicle's route, tries every 2-opt swap, accepts if the
     total tour length drops. Iterates to convergence.
  3. `solve_or_tools` — wraps Google OR-Tools' constraint-programming
     routing solver if `ortools` is installed. Gracefully degrades
     to a 2-opt solve if the import fails.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Final

import numpy as np

# Default per-agent cap mirrors logistics.DEFAULT_CARGO_CAPACITY. We
# do not import it to keep this module independent of the rest of
# the logistics layer (it operates on the data classes below only).
DEFAULT_CAPACITY: Final[int] = 20


class VRPError(Exception):
    """Base error for VRP construction / solving."""


@dataclass(frozen=True, slots=True)
class VRPOrder:
    """A single pending delivery for the VRP."""

    order_id: int
    node: int
    quantity: int
    reward: float = 0.0


@dataclass(frozen=True, slots=True)
class VRPInstance:
    """Snapshot of the routing problem at a point in time.

    `distance_matrix[i, j]` is the cost of travelling from node `i` to
    node `j` and is assumed symmetric and non-negative. Node ids are
    INDEXES into the matrix — callers map arena-node-id ↔ matrix-index
    themselves (see `compute_vrp_baseline` in the orchestrator).
    """

    n_nodes: int
    distance_matrix: np.ndarray  # shape (n_nodes, n_nodes), float
    orders: tuple[VRPOrder, ...]
    agent_start: tuple[int, ...]  # per-agent starting node index
    agent_capacity: tuple[int, ...]  # per-agent cargo cap

    def __post_init__(self) -> None:
        if self.distance_matrix.shape != (self.n_nodes, self.n_nodes):
            raise VRPError(
                f"distance_matrix shape {self.distance_matrix.shape} does not match n_nodes={self.n_nodes}"
            )
        if len(self.agent_start) != len(self.agent_capacity):
            raise VRPError("agent_start and agent_capacity must have the same length")
        for order in self.orders:
            if not (0 <= order.node < self.n_nodes):
                raise VRPError(f"order {order.order_id} node {order.node} out of range")
        for idx, start in enumerate(self.agent_start):
            if not (0 <= start < self.n_nodes):
                raise VRPError(f"agent {idx} start {start} out of range")

    @property
    def n_agents(self) -> int:
        return len(self.agent_start)


@dataclass(frozen=True, slots=True)
class VRPSolution:
    """Result of solving a `VRPInstance`."""

    routes: tuple[tuple[int, ...], ...]
    # `routes[i]` is the sequence of NODE INDEXES vehicle i visits AFTER
    # leaving its start node, in order. Empty tuple means the vehicle
    # stays at its start.
    served_order_ids: tuple[int, ...]
    unserved_order_ids: tuple[int, ...]
    total_cost: float
    per_agent_cost: tuple[float, ...]
    solver: str
    compute_time_ms: float
    metadata: dict[str, float | str] = field(default_factory=dict)


# ── distance / route utilities ──────────────────────────────────────


def _route_length(
    distance_matrix: np.ndarray,
    start: int,
    visited_nodes: tuple[int, ...],
) -> float:
    if not visited_nodes:
        return 0.0
    total = float(distance_matrix[start, visited_nodes[0]])
    for i in range(len(visited_nodes) - 1):
        total += float(distance_matrix[visited_nodes[i], visited_nodes[i + 1]])
    return total


def _solution_cost(
    instance: VRPInstance,
    routes_with_order_ids: list[list[tuple[int, int]]],
) -> tuple[float, tuple[float, ...]]:
    """Total + per-agent cost given per-agent (node, order_id) sequences."""
    per_agent: list[float] = []
    for agent_idx, route in enumerate(routes_with_order_ids):
        nodes = tuple(node for node, _ in route)
        per_agent.append(
            _route_length(instance.distance_matrix, instance.agent_start[agent_idx], nodes)
        )
    return float(sum(per_agent)), tuple(per_agent)


# ── solver 1: greedy nearest neighbor ───────────────────────────────


def solve_greedy_nearest_neighbor(instance: VRPInstance) -> VRPSolution:
    """Per-agent nearest-feasible-order until capacity or orders run out.

    Each step picks the open order whose `distance_matrix[current,
    order.node] / max(1, reward)` is smallest, with capacity respected.
    """
    t0 = time.perf_counter()
    remaining: dict[int, VRPOrder] = {o.order_id: o for o in instance.orders}
    routes: list[list[tuple[int, int]]] = [[] for _ in range(instance.n_agents)]
    remaining_capacity = list(instance.agent_capacity)
    current_pos = list(instance.agent_start)

    # Round-robin across agents so no single agent monopolises every order.
    # Each agent picks one order per round; round terminates when no
    # agent could pick anything in the previous pass.
    while remaining:
        progressed = False
        for agent_idx in range(instance.n_agents):
            if not remaining:
                break
            cap = remaining_capacity[agent_idx]
            if cap <= 0:
                continue
            cur = current_pos[agent_idx]
            best_id: int | None = None
            best_cost = float("inf")
            for oid, order in remaining.items():
                if order.quantity > cap:
                    continue
                d = float(instance.distance_matrix[cur, order.node])
                if d < best_cost:
                    best_cost = d
                    best_id = oid
            if best_id is None:
                continue
            order = remaining.pop(best_id)
            routes[agent_idx].append((order.node, order.order_id))
            current_pos[agent_idx] = order.node
            remaining_capacity[agent_idx] = cap - order.quantity
            progressed = True
        if not progressed:
            break

    served_ids: list[int] = []
    for r in routes:
        served_ids.extend(oid for _, oid in r)
    unserved_ids = [o.order_id for o in instance.orders if o.order_id not in served_ids]
    total, per_agent = _solution_cost(instance, routes)
    return VRPSolution(
        routes=tuple(tuple(node for node, _ in r) for r in routes),
        served_order_ids=tuple(served_ids),
        unserved_order_ids=tuple(unserved_ids),
        total_cost=total,
        per_agent_cost=per_agent,
        solver="greedy_nearest_neighbor",
        compute_time_ms=(time.perf_counter() - t0) * 1000.0,
    )


# ── solver 2: 2-opt improvement ─────────────────────────────────────


def _two_opt_single_route(distance_matrix: np.ndarray, start: int, nodes: list[int]) -> list[int]:
    """Run 2-opt swaps on one route to convergence."""
    if len(nodes) < 2:
        return nodes
    improved = True
    while improved:
        improved = False
        best_len = _route_length(distance_matrix, start, tuple(nodes))
        for i in range(len(nodes) - 1):
            for j in range(i + 1, len(nodes)):
                candidate = nodes[:i] + list(reversed(nodes[i : j + 1])) + nodes[j + 1 :]
                cand_len = _route_length(distance_matrix, start, tuple(candidate))
                if cand_len + 1e-12 < best_len:
                    nodes = candidate
                    best_len = cand_len
                    improved = True
                    break
            if improved:
                break
    return nodes


def solve_two_opt(
    instance: VRPInstance,
    initial: VRPSolution | None = None,
) -> VRPSolution:
    """Improve an initial solution (default: greedy) via per-route 2-opt swaps."""
    t0 = time.perf_counter()
    if initial is None:
        initial = solve_greedy_nearest_neighbor(instance)
    # We need (node, order_id) sequences to preserve order_id mapping
    # across swaps. Rebuild from the served ids in initial.routes order.
    served_lookup: dict[int, int] = {}
    served_iter = iter(initial.served_order_ids)
    for route in initial.routes:
        for node in route:
            try:
                oid = next(served_iter)
                served_lookup[oid] = node
            except StopIteration:
                break
    new_routes: list[tuple[int, ...]] = []
    new_served: list[int] = []
    # Iterate per-agent: for each route, get the list of (node, oid)
    # tuples, run 2-opt on the node sequence, then re-derive oid order.
    served_iter = iter(initial.served_order_ids)
    for agent_idx, route in enumerate(initial.routes):
        route_oids: list[int] = []
        for _node in route:
            try:
                route_oids.append(next(served_iter))
            except StopIteration:
                break
        if len(route) < 2:
            new_routes.append(route)
            new_served.extend(route_oids)
            continue
        # Pair (node, oid) so swaps keep the order_id assignment intact.
        paired = list(zip(route, route_oids, strict=True))
        nodes = [n for n, _ in paired]
        oid_by_node_position = list(range(len(nodes)))
        improved = True
        start = instance.agent_start[agent_idx]
        while improved:
            improved = False
            best_len = _route_length(instance.distance_matrix, start, tuple(nodes))
            for i in range(len(nodes) - 1):
                for j in range(i + 1, len(nodes)):
                    cand_nodes = nodes[:i] + list(reversed(nodes[i : j + 1])) + nodes[j + 1 :]
                    cand_pos = (
                        oid_by_node_position[:i]
                        + list(reversed(oid_by_node_position[i : j + 1]))
                        + oid_by_node_position[j + 1 :]
                    )
                    cand_len = _route_length(instance.distance_matrix, start, tuple(cand_nodes))
                    if cand_len + 1e-12 < best_len:
                        nodes = cand_nodes
                        oid_by_node_position = cand_pos
                        best_len = cand_len
                        improved = True
                        break
                if improved:
                    break
        new_routes.append(tuple(nodes))
        new_served.extend(paired[idx][1] for idx in oid_by_node_position)
    total = sum(
        _route_length(instance.distance_matrix, instance.agent_start[i], r)
        for i, r in enumerate(new_routes)
    )
    per_agent = tuple(
        _route_length(instance.distance_matrix, instance.agent_start[i], r)
        for i, r in enumerate(new_routes)
    )
    return VRPSolution(
        routes=tuple(new_routes),
        served_order_ids=tuple(new_served),
        unserved_order_ids=initial.unserved_order_ids,
        total_cost=float(total),
        per_agent_cost=per_agent,
        solver="two_opt",
        compute_time_ms=(time.perf_counter() - t0) * 1000.0,
        metadata={"initial_cost": initial.total_cost},
    )


# ── solver 3: Google OR-Tools (optional) ────────────────────────────


def solve_or_tools(
    instance: VRPInstance,
    time_limit_ms: int = 2000,
    distance_scale: float = 1000.0,
) -> VRPSolution:
    """Wrap Google OR-Tools' routing solver if `ortools` is installed.

    Gracefully degrades to `solve_two_opt` if the import fails. The
    distance matrix is scaled to integers because OR-Tools requires
    integer arc costs; `distance_scale=1000` gives 3 decimal digits
    of precision, which is plenty for our edge-cost magnitudes.
    """
    t0 = time.perf_counter()
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except ImportError:
        sol = solve_two_opt(instance)
        return VRPSolution(
            routes=sol.routes,
            served_order_ids=sol.served_order_ids,
            unserved_order_ids=sol.unserved_order_ids,
            total_cost=sol.total_cost,
            per_agent_cost=sol.per_agent_cost,
            solver="or_tools_fallback_two_opt",
            compute_time_ms=(time.perf_counter() - t0) * 1000.0,
            metadata={"reason": "ortools not installed"},
        )

    if not instance.orders:
        return VRPSolution(
            routes=tuple(() for _ in range(instance.n_agents)),
            served_order_ids=(),
            unserved_order_ids=(),
            total_cost=0.0,
            per_agent_cost=tuple(0.0 for _ in range(instance.n_agents)),
            solver="or_tools",
            compute_time_ms=(time.perf_counter() - t0) * 1000.0,
        )

    # Build OR-Tools index space: stops are [agent_starts..., order_nodes...]
    # OR-Tools requires each vehicle to have a start AND end index. We
    # use start = end = the agent's current node, modeled as the first
    # n_agents indices. Order nodes occupy the rest.
    starts = list(range(instance.n_agents))
    ends = list(range(instance.n_agents))
    n_stops = instance.n_agents + len(instance.orders)
    # Build a stop -> arena-node-index mapping.
    stop_node = list(instance.agent_start) + [o.node for o in instance.orders]
    # Demands by stop index: agent stops have 0 demand; order stops have order.quantity.
    demands = [0] * instance.n_agents + [o.quantity for o in instance.orders]

    manager = pywrapcp.RoutingIndexManager(n_stops, instance.n_agents, starts, ends)
    routing = pywrapcp.RoutingModel(manager)

    def _distance_callback(from_index: int, to_index: int) -> int:
        from_stop = manager.IndexToNode(from_index)
        to_stop = manager.IndexToNode(to_index)
        d = float(instance.distance_matrix[stop_node[from_stop], stop_node[to_stop]])
        return int(d * distance_scale)

    transit_idx = routing.RegisterTransitCallback(_distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    def _demand_callback(from_index: int) -> int:
        from_stop = manager.IndexToNode(from_index)
        return demands[from_stop]

    demand_idx = routing.RegisterUnaryTransitCallback(_demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_idx,
        0,
        list(instance.agent_capacity),
        True,
        "Capacity",
    )
    # Allow orders to be dropped (penalty large enough to prefer serving).
    penalty = int(distance_scale * float(instance.distance_matrix.max()) * n_stops)
    for stop_idx in range(instance.n_agents, n_stops):
        routing.AddDisjunction([manager.NodeToIndex(stop_idx)], penalty)

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_params.time_limit.FromMilliseconds(time_limit_ms)

    assignment = routing.SolveWithParameters(search_params)
    if assignment is None:
        # OR-Tools couldn't find anything; fall back to two-opt.
        sol = solve_two_opt(instance)
        return VRPSolution(
            routes=sol.routes,
            served_order_ids=sol.served_order_ids,
            unserved_order_ids=sol.unserved_order_ids,
            total_cost=sol.total_cost,
            per_agent_cost=sol.per_agent_cost,
            solver="or_tools_fallback_two_opt",
            compute_time_ms=(time.perf_counter() - t0) * 1000.0,
            metadata={"reason": "or-tools solver returned no assignment"},
        )

    routes_node: list[tuple[int, ...]] = []
    routes_oid: list[int] = []
    per_agent_cost: list[float] = []
    for v in range(instance.n_agents):
        index = routing.Start(v)
        path_stops: list[int] = []
        while not routing.IsEnd(index):
            stop_idx = manager.IndexToNode(index)
            if stop_idx >= instance.n_agents:
                # An order stop; record both the node and its order id.
                order = instance.orders[stop_idx - instance.n_agents]
                path_stops.append(order.node)
                routes_oid.append(order.order_id)
            index = assignment.Value(routing.NextVar(index))
        routes_node.append(tuple(path_stops))
        per_agent_cost.append(
            _route_length(instance.distance_matrix, instance.agent_start[v], tuple(path_stops))
        )

    served = set(routes_oid)
    unserved = tuple(o.order_id for o in instance.orders if o.order_id not in served)
    return VRPSolution(
        routes=tuple(routes_node),
        served_order_ids=tuple(routes_oid),
        unserved_order_ids=unserved,
        total_cost=float(sum(per_agent_cost)),
        per_agent_cost=tuple(per_agent_cost),
        solver="or_tools",
        compute_time_ms=(time.perf_counter() - t0) * 1000.0,
    )


# ── arena-aware helpers ─────────────────────────────────────────────


def build_arena_distance_matrix(arena: object) -> tuple[np.ndarray, tuple[int, ...]]:
    """All-pairs shortest-path distance matrix over the arena graph.

    Returns the matrix plus the canonical node ordering (matrix index → arena node id).
    """
    import networkx as nx

    graph = arena.graph  # type: ignore[attr-defined]
    nodes = sorted(int(n) for n in graph.nodes())
    n = len(nodes)
    idx = {node: i for i, node in enumerate(nodes)}
    mat = np.full((n, n), float("inf"))
    # Use edge_cost attribute if exposed by arena; else fall back to 1.0.
    edge_cost: dict[tuple[int, int], float] = getattr(arena, "edge_cost", {})

    def weight(u: int, v: int, _data: object) -> float:
        key = (u, v) if u <= v else (v, u)
        return float(edge_cost.get(key, 1.0))

    for src in nodes:
        lengths = nx.single_source_dijkstra_path_length(graph, src, weight=weight)
        for dst, dist in lengths.items():
            mat[idx[src], idx[int(dst)]] = float(dist)
    np.fill_diagonal(mat, 0.0)
    return mat, tuple(nodes)
