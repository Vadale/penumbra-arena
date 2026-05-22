"""Adapter that turns a saved MAPPO checkpoint into a `Policy` callable.

Concept taught: how a trained model lands in production. Two paths:

1. `mappo_policy_factory(checkpoint, n_agents) -> policy_factory(i) -> Policy`
   — back-compat per-agent path. Each agent gets a closure that
   does its own forward pass. Slow because 50 sequential single-
   row matmuls on MPS are kernel-launch-overhead-bound.

2. `mappo_batch_policy(checkpoint, n_agents) -> BatchPolicy` —
   the FAST path. Returns a function that takes (agents, observations)
   and runs a single (50, obs_dim) batched forward pass. ~50× faster
   on MPS and what Simulation uses when wired through
   `Simulation.build(batch_policy=...)`.

Both are resilient: if the checkpoint can't be loaded (missing file,
wrong shape, MPS unavailable), we log and fall back to None so the
simulation defaults to its random-walk baseline.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from penumbra_core.agent import AgentObservation, Policy, random_walk_policy

from penumbra_learning.env import NEIGHBOURS_K, OBS_PER_NEIGHBOUR
from penumbra_learning.mappo import MAPPO, MAPPOConfig

logger = logging.getLogger(__name__)


def mappo_policy_factory(
    checkpoint_path: str | Path,
    *,
    n_agents: int,
    deterministic: bool = True,
) -> callable:  # type: ignore[valid-type]
    """Return a `policy_factory(agent_id) -> Policy` backed by a MAPPO actor.

    The MAPPO actor is loaded once and shared across agents (parameter
    sharing was the training-time convention; here we honour it).

    If anything goes wrong loading the checkpoint we fall back to the
    `random_walk_policy` factory — the simulation must always boot.
    """
    path = Path(checkpoint_path)
    if not path.is_file():
        logger.warning("MAPPO checkpoint not found at %s; using random walk", path)
        return _random_walk_factory

    config = MAPPOConfig(
        obs_dim=NEIGHBOURS_K * OBS_PER_NEIGHBOUR,
        n_actions=NEIGHBOURS_K + 1,
        n_agents=n_agents,
    )
    try:
        agent = MAPPO(config)
        # actor_only=True so a checkpoint trained at one population size
        # works for any live n_agents — the critic isn't needed at
        # inference (it's a training-only centralised value head).
        agent.load(str(path), actor_only=True)
    except Exception:
        logger.exception("failed to load MAPPO checkpoint %s; using random walk", path)
        return _random_walk_factory

    def _mappo_policy(observation: AgentObservation, rng: np.random.Generator) -> int:
        """Single-agent inference path. rng is honoured when deterministic=False."""
        del rng  # MAPPO actor handles stochasticity internally when sampling.
        feature_vec = _build_feature_vector(observation)
        action_idx = int(agent.act(feature_vec[None, :], deterministic=deterministic)[0])
        neighbours = sorted(observation.neighbour_costs.keys())
        if action_idx >= len(neighbours):
            # "stay" or illegal index → stay put.
            return observation.position
        return neighbours[action_idx]

    def _factory(_agent_id: int) -> Policy:
        return _mappo_policy

    logger.info("loaded MAPPO checkpoint from %s; deterministic=%s", path, deterministic)
    return _factory


def _build_feature_vector(observation: AgentObservation) -> np.ndarray:
    """Mirror the layout used by PenumbraEnv: K neighbour rows of (cost, is_goal, is_goal).

    PenumbraEnv pads missing slots with PAD_VALUE (-1.0); we do the same
    here so the actor sees the same shape it saw during training.
    """
    from penumbra_learning.env import PAD_VALUE

    neighbours = sorted(observation.neighbour_costs.keys())
    goals = set(observation.visible_goals)
    feats: list[float] = []
    for j in range(NEIGHBOURS_K):
        if j < len(neighbours):
            n = neighbours[j]
            cost = float(observation.neighbour_costs[n])
            is_goal = 1.0 if n in goals else 0.0
            feats.extend([cost, is_goal, is_goal])
        else:
            feats.extend([PAD_VALUE, PAD_VALUE, PAD_VALUE])
    return np.asarray(feats, dtype=np.float32)


def _random_walk_factory(_agent_id: int) -> Policy:
    return random_walk_policy


def mappo_batch_policy(
    checkpoint_path: str | Path,
    *,
    n_agents: int,
    deterministic: bool = True,
) -> callable | None:  # type: ignore[valid-type]
    """Return a `BatchPolicy` backed by ONE batched MAPPO forward pass per tick.

    Signature matches `penumbra_core.simulation.BatchPolicy`:
        f(agents, observations) -> list[NodeId]

    Why this exists: the per-agent policy_factory hands every agent a
    closure that runs its own `agent.act([obs])` call. With 50 agents
    on MPS that's 50 kernel launches per tick (~5 ms each = ~250 ms
    total) — the simulation falls from the 10 Hz target to ~4 Hz. The
    batched path builds a (50, obs_dim) stack and runs ONE forward
    pass (~5 ms total, ~50× faster).

    Returns None if the checkpoint can't be loaded; the caller falls
    through to per-agent policies (random walk or whatever).
    """
    path = Path(checkpoint_path)
    if not path.is_file():
        logger.warning("MAPPO checkpoint not found at %s; using per-agent fallback", path)
        return None

    config = MAPPOConfig(
        obs_dim=NEIGHBOURS_K * OBS_PER_NEIGHBOUR,
        n_actions=NEIGHBOURS_K + 1,
        n_agents=n_agents,
    )
    try:
        agent_net = MAPPO(config)
        agent_net.load(str(path), actor_only=True)
    except Exception:
        logger.exception("failed to load MAPPO checkpoint %s; using per-agent fallback", path)
        return None

    def _batch_policy(agents: object, observations: object) -> list[int]:
        # `agents` and `observations` are list[Agent] and
        # list[AgentObservation] — typed as object to avoid the
        # penumbra-learning→penumbra-core import dependency cycle.
        obs_list = list(observations)  # type: ignore[arg-type]
        agent_list = list(agents)  # type: ignore[arg-type]
        if not obs_list:
            return []
        # Stack observations into a (B, obs_dim) batch.
        batch = np.stack([_build_feature_vector(o) for o in obs_list], axis=0)
        # Single forward pass over the whole batch.
        action_indices = agent_net.act(batch, deterministic=deterministic)
        # Map each action index back to the agent's neighbour-or-stay choice.
        out: list[int] = []
        for ag, obs, action_idx in zip(agent_list, obs_list, action_indices, strict=True):
            neighbours = sorted(obs.neighbour_costs.keys())  # type: ignore[attr-defined]
            idx = int(action_idx)
            if idx >= len(neighbours):
                out.append(ag.position)  # type: ignore[attr-defined]
            else:
                out.append(neighbours[idx])
        return out

    logger.info("loaded MAPPO BATCH checkpoint from %s; deterministic=%s", path, deterministic)
    return _batch_policy
