"""PettingZoo ParallelEnv wrapping `penumbra_core.Simulation`.

Concept taught: how a domain simulation is *adapted* to the standard
multi-agent RL interface. We expose:
- `agents`: a list of stable string IDs ("agent_0", "agent_1", …).
- `observation_space[agent]`: a fixed-size Box of neighbour-cost
  features (padded so the action dimensionality is constant).
- `action_space[agent]`: a Discrete over the top-K neighbours.
- `reset()` -> per-agent obs dict.
- `step(actions)` -> (obs, rewards, terminations, truncations, infos).

Reward shaping:
- -0.01 per tick (encourage finishing).
- +1.0 for the agent that reaches a goal.
- -0.1 if the agent attempts an illegal move (stays in place).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, cast

import numpy as np
from gymnasium.spaces import Box, Discrete
from numpy.typing import NDArray
from penumbra_core.arena import ArenaConfig
from penumbra_core.rng import Seeded, bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from pettingzoo import ParallelEnv

# Observation: K nearest neighbours, each (edge_cost, is_goal, goal_distance_approx).
# Pad with sentinel −1 when fewer than K neighbours.
NEIGHBOURS_K = 6
OBS_PER_NEIGHBOUR = 3
PAD_VALUE = -1.0


@dataclass(slots=True)
class RewardWeights:
    """Tunable reward components used by the env on every step.

    The user can mutate these at runtime via /learning/reward-weights;
    the live trainer picks the new values up at the next iteration
    because the env reads them through a shared singleton.
    """

    goal_reward: float = 1.0
    step_penalty: float = -0.01
    illegal_move_penalty: float = -0.1
    crowding_penalty: float = 0.0  # per agent on the same node, applied to all of them


# Module-level singleton — the simplest way to share live-mutable weights
# between the API endpoint and N PenumbraEnv instances. The endpoint
# mutates fields in place; envs read them at step() time.
REWARD_WEIGHTS = RewardWeights()


class PenumbraEnv(ParallelEnv):  # type: ignore[misc]
    """Penumbra simulation as a PettingZoo ParallelEnv."""

    metadata: ClassVar[dict[str, Any]] = {"render_modes": [], "name": "penumbra_v0"}

    def __init__(
        self,
        *,
        n_agents: int = 20,
        arena_nodes: int = 25,
        max_match_ticks: int = 200,
        seed: int = 42,
    ) -> None:
        super().__init__()
        self._n_agents = n_agents
        self._arena_nodes = arena_nodes
        self._max_match_ticks = max_match_ticks
        self._seed = seed

        self.agents: list[str] = []
        self.possible_agents: list[str] = [f"agent_{i}" for i in range(n_agents)]
        self.observation_spaces = {
            agent: Box(
                low=PAD_VALUE,
                high=np.inf,
                shape=(NEIGHBOURS_K * OBS_PER_NEIGHBOUR,),
                dtype=np.float32,
            )
            for agent in self.possible_agents
        }
        self.action_spaces = {
            agent: Discrete(NEIGHBOURS_K + 1)  # K neighbours + "stay"
            for agent in self.possible_agents
        }
        self._sim: Simulation | None = None
        self._seeded: Seeded | None = None
        self._neighbour_index: dict[int, list[int]] = {}

    def reset(
        self, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[dict[str, NDArray[np.float32]], dict[str, dict[str, Any]]]:
        effective_seed = seed if seed is not None else self._seed
        self._seeded = bootstrap(effective_seed)
        self._sim = Simulation.build(
            SimulationConfig(
                n_agents=self._n_agents,
                arena=ArenaConfig(n_nodes=self._arena_nodes),
                match_max_ticks=self._max_match_ticks,
            ),
            self._seeded,
        )
        self.agents = list(self.possible_agents)
        observations = {agent: self._observe(i) for i, agent in enumerate(self.possible_agents)}
        infos: dict[str, dict[str, Any]] = {agent: {} for agent in self.possible_agents}
        return observations, infos

    def step(
        self, actions: dict[str, int]
    ) -> tuple[
        dict[str, NDArray[np.float32]],
        dict[str, float],
        dict[str, bool],
        dict[str, bool],
        dict[str, dict[str, Any]],
    ]:
        assert self._sim is not None, "call reset() before step()"
        sim = self._sim

        rewards: dict[str, float] = dict.fromkeys(self.agents, REWARD_WEIGHTS.step_penalty)
        # Snapshot pre-step positions / goals to score legality and wins.
        pre_positions = {i: sim.agents[i].position for i in range(self._n_agents)}
        goal_set_pre = set(sim.arena.goals)

        # Override each agent's policy choice for this tick.
        for i, agent_str in enumerate(self.possible_agents):
            action = actions.get(agent_str, NEIGHBOURS_K)  # default: stay
            self._apply_action(i, action, pre_positions[i], rewards, agent_str)

        # Advance one simulation tick (arena dynamics + match check).
        # Agents have already moved above; we still call tick() to advance
        # the arena OU + match accounting. To avoid double-moving, we wipe
        # the simulation's policy outputs by setting a no-op policy.
        sim.arena.step()
        if sim.tick_counter > 0 and sim.tick_counter % 1 == 0:
            pass  # NOP placeholder for symmetry
        sim.tick_counter += 1
        sim._evaluate_match()

        # Win reward: any agent currently on a goal.
        post_goals = set(sim.arena.goals)
        for i, agent_str in enumerate(self.possible_agents):
            if sim.agents[i].position in post_goals or sim.agents[i].position in goal_set_pre:
                rewards[agent_str] += REWARD_WEIGHTS.goal_reward
        # Anti-crowding penalty: count agents per node, apply weighted
        # penalty proportional to (count - 1).
        if REWARD_WEIGHTS.crowding_penalty != 0.0:
            counts: dict[int, int] = {}
            for i in range(self._n_agents):
                counts[sim.agents[i].position] = counts.get(sim.agents[i].position, 0) + 1
            for i, agent_str in enumerate(self.possible_agents):
                excess = max(0, counts[sim.agents[i].position] - 1)
                if excess > 0:
                    rewards[agent_str] += REWARD_WEIGHTS.crowding_penalty * excess

        terminated = dict.fromkeys(self.agents, sim.current_match.is_over)
        truncated = dict.fromkeys(self.agents, False)
        if all(terminated.values()):
            self.agents = []
        observations = {agent: self._observe(i) for i, agent in enumerate(self.possible_agents)}
        infos: dict[str, dict[str, Any]] = {agent: {} for agent in self.possible_agents}
        return observations, rewards, terminated, truncated, infos

    def observation_space(self, agent: str) -> Box:  # type: ignore[override]
        return cast(Box, self.observation_spaces[agent])

    def action_space(self, agent: str) -> Discrete:  # type: ignore[override]
        return cast(Discrete, self.action_spaces[agent])

    # ── internals ────────────────────────────────────────────────────

    def _observe(self, agent_idx: int) -> NDArray[np.float32]:
        assert self._sim is not None
        sim = self._sim
        agent = sim.agents[agent_idx]
        neighbours = sorted(sim.arena.neighbours(agent.position))
        self._neighbour_index[agent_idx] = neighbours
        goals = set(sim.arena.goals)
        features: list[float] = []
        for j in range(NEIGHBOURS_K):
            if j < len(neighbours):
                n = neighbours[j]
                cost = float(sim.arena.cost_of(agent.position, n))
                is_goal = 1.0 if n in goals else 0.0
                # Rough goal proximity: 1 if neighbour is a goal, else 0.
                features.extend([cost, is_goal, is_goal])
            else:
                features.extend([PAD_VALUE, PAD_VALUE, PAD_VALUE])
        return np.asarray(features, dtype=np.float32)

    def _apply_action(
        self,
        agent_idx: int,
        action: int,
        pre_position: int,
        rewards: dict[str, float],
        agent_str: str,
    ) -> None:
        assert self._sim is not None
        sim = self._sim
        if action == NEIGHBOURS_K:  # explicit "stay"
            return
        neighbours = self._neighbour_index.get(agent_idx, [])
        if action >= len(neighbours):
            rewards[agent_str] += REWARD_WEIGHTS.illegal_move_penalty
            return
        target = neighbours[action]
        cost = sim.arena.cost_of(pre_position, target)
        sim.agents[agent_idx].move_to(target, cost, tick=sim.tick_counter)
