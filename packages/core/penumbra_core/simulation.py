"""Perpetual simulation tick loop — the integration seam.

Concept taught: *integration seam*. Every Penumbra pillar (NN, crypto, stats,
linalg, topology, chain) attaches a callback or consumer to the simulation
tick. This module exposes the seam and the lifecycle (pause / step /
time-warp / restart) — nothing else.

The loop is pure Python and synchronous; the async streaming layer lives in
`penumbra-transport`. This separation lets us property-test the loop without
spinning up FastAPI.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from penumbra_core.agent import Agent, AgentObservation
from penumbra_core.arena import Arena, ArenaConfig, NodeId
from penumbra_core.match import Match, MatchStatus
from penumbra_core.rng import Seeded


class RunState(StrEnum):
    """Coarse run-state of the simulation, controlled from outside."""

    RUNNING = "running"
    PAUSED = "paused"
    STEPPING = "stepping"


@dataclass(slots=True)
class TickFrame:
    """Snapshot emitted at the end of every tick — consumed by transport."""

    tick: int
    match_id: int
    match_status: MatchStatus
    agent_positions: dict[int, NodeId]
    arena_edge_count: int
    arena_goals: list[NodeId]


@dataclass(slots=True)
class SimulationConfig:
    """Parameters governing the perpetual loop."""

    n_agents: int = 50
    arena: ArenaConfig = field(default_factory=ArenaConfig)
    match_max_ticks: int = 1_200
    time_warp: int = 1
    """How many simulation ticks per `tick()` call. 1 means real-time; higher
    means fast-forward."""


@dataclass(slots=True)
class Simulation:
    """Perpetual multi-agent simulation. Owns arena, agents, current match."""

    config: SimulationConfig
    seeded: Seeded
    arena: Arena
    agents: list[Agent]
    current_match: Match
    next_match_id: int = 1
    tick_counter: int = 0
    state: RunState = RunState.RUNNING
    on_match_end: Callable[[Match, Arena, list[Agent]], None] | None = None

    @classmethod
    def build(
        cls,
        config: SimulationConfig,
        seeded: Seeded,
        *,
        policy_factory: Callable[[int], Callable[[AgentObservation, object], NodeId]] | None = None,
    ) -> Simulation:
        """Construct a freshly-seeded simulation ready for tick 0."""
        from penumbra_core.agent import random_walk_policy

        arena = Arena.build(config.arena, seeded)
        rng = seeded.numpy_for("agents-init")
        n_nodes = arena.graph.number_of_nodes()
        spawn_nodes = rng.integers(0, n_nodes, size=config.n_agents).tolist()

        policy_fn = policy_factory or (lambda _: random_walk_policy)  # type: ignore[return-value]
        agents = [
            Agent(id=i, position=spawn_nodes[i], policy=policy_fn(i), home=spawn_nodes[i])
            for i in range(config.n_agents)
        ]

        return cls(
            config=config,
            seeded=seeded,
            arena=arena,
            agents=agents,
            current_match=Match.start(match_id=0, current_tick=0, max_ticks=config.match_max_ticks),
        )

    # ── lifecycle controls ────────────────────────────────────────────

    def pause(self) -> None:
        self.state = RunState.PAUSED

    def resume(self) -> None:
        self.state = RunState.RUNNING

    def step_once(self) -> TickFrame:
        """Run exactly one tick regardless of pause state."""
        previous_state = self.state
        self.state = RunState.STEPPING
        frame = self._tick()
        self.state = previous_state if previous_state is not RunState.STEPPING else RunState.PAUSED
        return frame

    def tick(self) -> TickFrame | None:
        """Advance the simulation by `time_warp` ticks; return last frame.

        Returns None if the simulation is paused (no ticks executed).
        """
        if self.state is RunState.PAUSED:
            return None
        frame: TickFrame | None = None
        for _ in range(self.config.time_warp):
            frame = self._tick()
        return frame

    # ── internals ────────────────────────────────────────────────────

    def _tick(self) -> TickFrame:
        """One discrete tick: arena advances, agents act, match status checked."""
        self.arena.step()
        self._move_agents()
        self._evaluate_match()
        self.tick_counter += 1
        return self._snapshot()

    def _move_agents(self) -> None:
        for agent in self.agents:
            observation = agent.observe(self.arena, tick=self.tick_counter)
            agent_rng = self.seeded.numpy_for(f"agent-{agent.id}")
            target = agent.policy(observation, agent_rng)
            if target == agent.position:
                continue
            if target not in observation.neighbour_costs:
                # Policy proposed an illegal move; stay put.
                continue
            cost = observation.neighbour_costs[target]
            agent.move_to(target, cost, tick=self.tick_counter)

    def _evaluate_match(self) -> None:
        match = self.current_match
        # Win condition: any agent on a goal node.
        goal_set = set(self.arena.goals)
        for agent in self.agents:
            if agent.position in goal_set:
                match.declare_winner(agent.id, agent.position, tick=self.tick_counter)
                self._begin_new_match(reason="won")
                return
        # Expiry condition: tick budget exhausted.
        if match.ticks_elapsed(self.tick_counter) >= match.max_ticks:
            match.expire(tick=self.tick_counter)
            self._begin_new_match(reason="expired")

    def _begin_new_match(self, *, reason: str) -> None:
        if self.on_match_end is not None:
            self.on_match_end(self.current_match, self.arena, self.agents)
        # Light arena perturbation so consecutive matches don't share the same
        # initial conditions even though the topology persists.
        self.arena.step_n(5)
        self.current_match = Match.start(
            match_id=self.next_match_id,
            current_tick=self.tick_counter,
            max_ticks=self.config.match_max_ticks,
        )
        self.current_match.metadata["previous_end_reason"] = reason
        self.next_match_id += 1

    def _snapshot(self) -> TickFrame:
        return TickFrame(
            tick=self.tick_counter,
            match_id=self.current_match.id,
            match_status=self.current_match.status,
            agent_positions={a.id: a.position for a in self.agents},
            arena_edge_count=self.arena.graph.number_of_edges(),
            arena_goals=list(self.arena.goals),
        )
