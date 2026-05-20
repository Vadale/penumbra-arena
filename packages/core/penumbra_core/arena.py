"""Procedurally dynamic graph world.

Concept taught: SDE-driven graph dynamics. The arena is a graph whose edge
weights follow Ornstein-Uhlenbeck processes (mean-reverting noise), whose
goal nodes random-walk along the topology, and whose edges occasionally
flip on/off ("weather"). Together these guarantee that no *static* shortest
path exists — the path you computed two ticks ago is no longer the cheapest.

The arena holds no I/O. All randomness comes from `penumbra_core.rng`.
Determinism: given the same `Seeded` and the same call sequence, the world
evolves identically.

References
----------
- Uhlenbeck & Ornstein, "On the theory of the Brownian motion" (1930).
- Watts & Strogatz, "Collective dynamics of small-world networks" (1998).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
from numpy.random import Generator

from penumbra_core.rng import Seeded

NodeId = int
Edge = tuple[NodeId, NodeId]


@dataclass(frozen=True, slots=True)
class ArenaConfig:
    """Parameters governing the procedural arena.

    `n_nodes`           number of nodes in the graph
    `ring_neighbours`   k parameter of Watts-Strogatz (must be even)
    `rewire_prob`       Watts-Strogatz rewiring probability
    `n_goals`           how many goal nodes exist simultaneously
    `ou_theta`          OU mean-reversion strength on edge cost
    `ou_mu`             OU long-run mean of edge cost
    `ou_sigma`          OU diffusion coefficient
    `ou_dt`             discrete OU time step (in simulation seconds)
    `ou_floor`          lower bound clamp on edge cost (must be > 0)
    `goal_walk_period`  ticks between goal random-walk steps
    `weather_prob`      per-tick probability of attempting one weather event
    """

    n_nodes: int = 50
    ring_neighbours: int = 4
    rewire_prob: float = 0.1
    n_goals: int = 3
    ou_theta: float = 0.4
    ou_mu: float = 1.0
    ou_sigma: float = 0.3
    ou_dt: float = 0.1
    ou_floor: float = 0.05
    goal_walk_period: int = 20
    weather_prob: float = 0.02


@dataclass(slots=True)
class Arena:
    """Procedural dynamic graph with OU edge costs and migrating goals.

    Construct via `Arena.build(config, seeded)` rather than instantiating
    directly so the initial graph is guaranteed connected and the OU state
    is initialised from the long-run mean plus a small jitter.
    """

    config: ArenaConfig
    graph: nx.Graph
    edge_cost: dict[Edge, float]
    goals: list[NodeId]
    tick: int = 0
    rng: Generator = field(default_factory=lambda: np.random.default_rng(0))

    @classmethod
    def build(cls, config: ArenaConfig, seeded: Seeded) -> Arena:
        """Construct a connected arena seeded for this run."""
        rng = seeded.numpy_for("arena")
        graph = _generate_connected_graph(config, rng)
        edge_cost: dict[Edge, float] = {
            _canon(u, v): float(config.ou_mu + 0.1 * config.ou_sigma * rng.standard_normal())
            for u, v in graph.edges()
        }
        # Clamp initial samples to the floor.
        for edge, cost in edge_cost.items():
            edge_cost[edge] = max(cost, config.ou_floor)
        goals = list(rng.choice(graph.number_of_nodes(), size=config.n_goals, replace=False))
        return cls(config=config, graph=graph, edge_cost=edge_cost, goals=goals, rng=rng)

    def step(self) -> None:
        """Advance one tick: OU on every edge, occasional weather, goal walk."""
        self._step_ou()
        if self.rng.random() < self.config.weather_prob:
            self._weather_event()
        if self.tick > 0 and self.tick % self.config.goal_walk_period == 0:
            self._migrate_goals()
        self.tick += 1

    def step_n(self, n: int) -> None:
        for _ in range(n):
            self.step()

    def cost_of(self, u: NodeId, v: NodeId) -> float:
        """Edge cost, or `+inf` if no such edge exists right now."""
        edge = _canon(u, v)
        return self.edge_cost.get(edge, math.inf)

    def neighbours(self, node: NodeId) -> list[NodeId]:
        return list(self.graph.neighbors(node))

    # ── internals ────────────────────────────────────────────────────

    def _step_ou(self) -> None:
        """Vectorised OU update on every edge cost."""
        if not self.edge_cost:
            return
        edges = list(self.edge_cost.keys())
        costs = np.fromiter((self.edge_cost[e] for e in edges), dtype=np.float64, count=len(edges))
        z = self.rng.standard_normal(costs.shape)
        drift = self.config.ou_theta * (self.config.ou_mu - costs) * self.config.ou_dt
        diffusion = self.config.ou_sigma * math.sqrt(self.config.ou_dt) * z
        new_costs = np.maximum(costs + drift + diffusion, self.config.ou_floor)
        for edge, value in zip(edges, new_costs.tolist(), strict=True):
            self.edge_cost[edge] = value

    def _weather_event(self) -> None:
        """Either delete a non-bridge edge or add a missing edge.

        Connectivity is preserved by rejecting deletions of bridges. Adding
        an edge is unconditional but only between currently non-adjacent
        node pairs.
        """
        nodes = list(self.graph.nodes())
        if self.rng.random() < 0.5 and self.graph.number_of_edges() > self.config.n_nodes:
            self._try_delete_edge()
        else:
            self._try_add_edge(nodes)

    def _try_delete_edge(self) -> None:
        edges = list(self.graph.edges())
        if not edges:
            return
        chosen_idx = int(self.rng.integers(0, len(edges)))
        u, v = edges[chosen_idx]
        # Skip the deletion if removing this edge would disconnect the graph.
        self.graph.remove_edge(u, v)
        if not nx.is_connected(self.graph):
            self.graph.add_edge(u, v)
            return
        self.edge_cost.pop(_canon(u, v), None)

    def _try_add_edge(self, nodes: list[NodeId]) -> None:
        u, v = self.rng.choice(nodes, size=2, replace=False).tolist()
        if u == v or self.graph.has_edge(u, v):
            return
        self.graph.add_edge(u, v)
        self.edge_cost[_canon(u, v)] = self.config.ou_mu

    def _migrate_goals(self) -> None:
        """Each goal jumps to a uniformly chosen neighbour."""
        new_goals: list[NodeId] = []
        for goal in self.goals:
            neighbours = list(self.graph.neighbors(goal))
            if not neighbours:
                new_goals.append(goal)
                continue
            choice_idx = int(self.rng.integers(0, len(neighbours)))
            new_goals.append(neighbours[choice_idx])
        self.goals = new_goals


def _generate_connected_graph(config: ArenaConfig, rng: Generator) -> nx.Graph:
    """Watts-Strogatz, retried until connected.

    We can't pass a `numpy.Generator` straight to networkx, so we seed
    networkx via the integer state of our own generator — this preserves
    determinism w.r.t. the parent `Seeded`.
    """
    for _ in range(64):
        seed = int(rng.integers(0, 2**31 - 1))
        graph: nx.Graph = nx.connected_watts_strogatz_graph(
            n=config.n_nodes,
            k=config.ring_neighbours,
            p=config.rewire_prob,
            tries=200,
            seed=seed,
        )
        if nx.is_connected(graph):
            return graph
    raise ArenaGenerationError("could not generate a connected arena within 64 attempts")


def _canon(u: NodeId, v: NodeId) -> Edge:
    """Canonical edge ordering — small endpoint first — for use as a dict key."""
    return (u, v) if u <= v else (v, u)


class ArenaGenerationError(RuntimeError):
    """Raised when the arena generator cannot produce a connected graph."""
