"""Self-play training loop for MAPPO.

Concept taught: rollout → update → checkpoint. The loop collects a
fixed-size batch from the environment, computes GAE advantages, runs
PPO updates, and periodically saves the checkpoint. With our small
nets and 20-agent env, each iteration is ~1s on M4 MPS.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from penumbra_learning.env import NEIGHBOURS_K, OBS_PER_NEIGHBOUR, PenumbraEnv
from penumbra_learning.mappo import MAPPO, MAPPOConfig


@dataclass(slots=True)
class TrainingConfig:
    n_iterations: int = 20
    rollout_length: int = 128
    checkpoint_every: int = 5
    checkpoint_path: str = "checkpoints/mappo_v0.pt"
    seed: int = 42


def train(
    env: PenumbraEnv,
    config: TrainingConfig | None = None,
) -> MAPPO:
    """Train MAPPO via self-play and return the agent."""
    cfg = config or TrainingConfig()
    obs_dim = NEIGHBOURS_K * OBS_PER_NEIGHBOUR
    n_actions = NEIGHBOURS_K + 1
    n_agents = env._n_agents

    agent = MAPPO(MAPPOConfig(obs_dim=obs_dim, n_actions=n_actions, n_agents=n_agents))
    device = agent.device

    obs_dict, _ = env.reset(seed=cfg.seed)

    for iteration in range(cfg.n_iterations):
        # Storage buffers for the rollout.
        obs_buf = torch.zeros((cfg.rollout_length, n_agents, obs_dim), device=device)
        global_obs_buf = torch.zeros((cfg.rollout_length, n_agents * obs_dim), device=device)
        actions_buf = torch.zeros((cfg.rollout_length, n_agents), dtype=torch.long, device=device)
        log_probs_buf = torch.zeros((cfg.rollout_length, n_agents), device=device)
        rewards_buf = torch.zeros((cfg.rollout_length,), device=device)
        values_buf = torch.zeros((cfg.rollout_length,), device=device)

        for t in range(cfg.rollout_length):
            obs_array = np.stack([obs_dict[a] for a in env.possible_agents])
            obs_t = torch.as_tensor(obs_array, dtype=torch.float32, device=device)
            global_obs_t = obs_t.reshape(-1)

            with torch.no_grad():
                dist = agent.actor(obs_t)
                action_t = dist.sample()
                log_prob = dist.log_prob(action_t)
                value = agent.critic(global_obs_t.unsqueeze(0)).squeeze(0)

            actions_dict = {a: int(action_t[i].item()) for i, a in enumerate(env.possible_agents)}
            next_obs_dict, rewards_dict, terminated, _truncated, _infos = env.step(actions_dict)

            obs_buf[t] = obs_t
            global_obs_buf[t] = global_obs_t
            actions_buf[t] = action_t
            log_probs_buf[t] = log_prob
            rewards_buf[t] = float(np.mean(list(rewards_dict.values())))
            values_buf[t] = value

            obs_dict = next_obs_dict
            if all(terminated.values()):
                obs_dict, _ = env.reset(seed=cfg.seed + iteration)

        # Bootstrap with the value of the last state.
        with torch.no_grad():
            last_obs_t = torch.as_tensor(
                np.stack([obs_dict[a] for a in env.possible_agents]),
                dtype=torch.float32,
                device=device,
            ).reshape(-1)
            last_value = agent.critic(last_obs_t.unsqueeze(0)).squeeze(0)

        advantages_step, returns_step = agent.compute_gae(
            rewards_buf,
            values_buf,
            last_value,
            agent.config.gamma,
            agent.config.gae_lambda,
        )
        advantages = advantages_step.unsqueeze(-1).expand(-1, n_agents)

        metrics = agent.update(
            obs_batch=obs_buf,
            global_obs_batch=global_obs_buf,
            actions_batch=actions_buf,
            log_probs_old=log_probs_buf,
            advantages=advantages,
            returns=returns_step,
        )

        if (iteration + 1) % cfg.checkpoint_every == 0:
            ckpt_path = Path(cfg.checkpoint_path)
            ckpt_path.parent.mkdir(parents=True, exist_ok=True)
            agent.save(str(ckpt_path))

        del obs_buf, global_obs_buf, actions_buf, log_probs_buf, rewards_buf, values_buf
        del metrics  # not logged here; tests assert convergence indirectly

    # Final checkpoint.
    ckpt_path = Path(cfg.checkpoint_path)
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    agent.save(str(ckpt_path))
    return agent
