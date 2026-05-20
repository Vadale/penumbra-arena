"""Agents and their policies.

Concept taught: a *policy* is just a pure function from observation to action.
Decoupling the policy from the agent lets us swap a random walk for MAPPO in
Phase 4 without touching the simulation loop.

The Phase 1 baseline policy is a uniform random walk over current neighbours;
later phases attach trained MAPPO actors with the same signature.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from numpy.random import Generator

    from penumbra_core.arena import Arena, NodeId


@dataclass(frozen=True, slots=True)
class AgentObservation:
    """What an agent sees on a tick.

    Phase 1 exposes positions and neighbour costs in clear. Later phases
    replace this with an encrypted view computed by `crypto/`.
    """

    agent_id: int
    position: NodeId
    neighbour_costs: dict[NodeId, float]
    visible_goals: list[NodeId]
    tick: int


Policy = Callable[[AgentObservation, "Generator"], "NodeId"]
"""Pure function: observation + RNG stream → next-node decision.

Implementations must be deterministic given the RNG; the simulation will
inject an agent-specific RNG stream so two policies never share state.
"""


@dataclass(slots=True)
class Agent:
    """A simulation agent. Position is a node id; policy decides the next hop."""

    id: int
    position: NodeId
    policy: Policy
    home: NodeId
    distance_travelled: float = 0.0
    last_action_tick: int = -1
    metadata: dict[str, str] = field(default_factory=dict)

    def observe(self, arena: Arena, tick: int) -> AgentObservation:
        """Build this agent's view of the world."""
        neighbours = arena.neighbours(self.position)
        return AgentObservation(
            agent_id=self.id,
            position=self.position,
            neighbour_costs={n: arena.cost_of(self.position, n) for n in neighbours},
            visible_goals=list(arena.goals),
            tick=tick,
        )

    def move_to(self, node: NodeId, cost: float, tick: int) -> None:
        """Apply a confirmed move (after the simulation validates legality)."""
        self.position = node
        self.distance_travelled += cost
        self.last_action_tick = tick


def random_walk_policy(observation: AgentObservation, rng: Generator) -> NodeId:
    """Pick a uniformly random neighbour; stay put if isolated."""
    neighbours = list(observation.neighbour_costs.keys())
    if not neighbours:
        return observation.position
    idx = int(rng.integers(0, len(neighbours)))
    return neighbours[idx]
