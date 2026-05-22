"""MAPPO (Multi-Agent PPO) — CleanRL-style, MPS-ready.

Concept taught: PPO on a multi-agent environment. MAPPO is "centralised
training, decentralised execution":

- **Actor** (per-agent, same weights — parameter sharing): sees only
  the agent's local observation, outputs an action distribution.
- **Critic** (centralised): sees the concatenated global observation
  during training, outputs a value estimate. At deployment, the critic
  is dropped — agents only need their actor.

PPO's clipped surrogate objective:
    L(θ) = E[ min(r(θ)·A, clip(r(θ), 1-ε, 1+ε)·A) ]
where r(θ) = π_θ(a|s) / π_θ_old(a|s) and A is the GAE advantage.

This implementation is intentionally small (~300 LOC, two-layer MLPs)
so the whole training loop fits in the user's mental model.

References
- Yu et al. "The surprising effectiveness of PPO in cooperative
  multi-agent games" (NeurIPS 2022). The MAPPO paper.
- Schulman et al. "Proximal policy optimization algorithms" (2017).
- CleanRL ppo_pettingzoo_ma_atari.py for the reference single-file
  style.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import torch
from torch import Tensor, nn
from torch.distributions.categorical import Categorical

from penumbra_learning.device import best_device


@dataclass(frozen=True, slots=True)
class MAPPOConfig:
    """Hyperparameters for the small-scale MAPPO trainer."""

    obs_dim: int
    n_actions: int
    n_agents: int
    hidden: int = 128
    learning_rate: float = 3e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_eps: float = 0.2
    ppo_epochs: int = 4
    minibatch_size: int = 256


class Actor(nn.Module):
    """Per-agent policy. Weights are shared across all agents."""

    def __init__(self, obs_dim: int, n_actions: int, hidden: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
            nn.Linear(hidden, n_actions),
        )

    def forward(self, obs: Tensor) -> Categorical:
        logits = self.net(obs)
        return Categorical(logits=logits)


class Critic(nn.Module):
    """Centralised value head — sees concatenated observations of all agents."""

    def __init__(self, global_obs_dim: int, hidden: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(global_obs_dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
            nn.Linear(hidden, 1),
        )

    def forward(self, global_obs: Tensor) -> Tensor:
        return self.net(global_obs).squeeze(-1)


class MAPPO:
    """MAPPO trainer + inference container."""

    def __init__(self, config: MAPPOConfig, device: torch.device | None = None) -> None:
        self.config = config
        self.device = device if device is not None else best_device()
        self.actor = Actor(config.obs_dim, config.n_actions, config.hidden).to(self.device)
        self.critic = Critic(
            global_obs_dim=config.obs_dim * config.n_agents,
            hidden=config.hidden,
        ).to(self.device)
        self.opt_actor = torch.optim.Adam(self.actor.parameters(), lr=config.learning_rate)
        self.opt_critic = torch.optim.Adam(self.critic.parameters(), lr=config.learning_rate)

    @torch.no_grad()
    def act(
        self,
        observations: np.ndarray,
        *,
        deterministic: bool = False,
        temperature: float = 1.0,
    ) -> np.ndarray:
        """Pick actions for a batch of (n_agents, obs_dim) observations.

        `temperature` scales the actor's logits before sampling. A
        well-trained policy concentrates probability mass on its best
        action; with parameter sharing across all N agents and the
        per-agent observations being similar, deterministic OR
        low-temperature sampling causes the swarm to collapse to one
        node. Setting temperature > 1.0 flattens the distribution and
        recovers exploratory dispersion at inference time without
        touching the trained weights.
        """
        obs_t = torch.as_tensor(observations, dtype=torch.float32, device=self.device)
        if deterministic:
            dist = self.actor(obs_t)
            actions = dist.probs.argmax(dim=-1)
        elif temperature == 1.0:
            dist = self.actor(obs_t)
            actions = dist.sample()
        else:
            # Rebuild Categorical from scaled logits.
            logits = self.actor.net(obs_t) / float(temperature)
            actions = Categorical(logits=logits).sample()
        return actions.cpu().numpy()

    def compute_gae(
        self,
        rewards: Tensor,
        values: Tensor,
        last_value: Tensor,
        gamma: float,
        gae_lambda: float,
    ) -> tuple[Tensor, Tensor]:
        """Generalised Advantage Estimation. Returns (advantages, returns)."""
        n_steps = rewards.size(0)
        advantages = torch.zeros_like(rewards)
        gae = torch.zeros_like(last_value)
        next_value = last_value
        for t in reversed(range(n_steps)):
            delta = rewards[t] + gamma * next_value - values[t]
            gae = delta + gamma * gae_lambda * gae
            advantages[t] = gae
            next_value = values[t]
        returns = advantages + values
        return advantages, returns

    def update(
        self,
        obs_batch: Tensor,  # (T, n_agents, obs_dim)
        global_obs_batch: Tensor,  # (T, n_agents * obs_dim)
        actions_batch: Tensor,  # (T, n_agents)
        log_probs_old: Tensor,  # (T, n_agents)
        advantages: Tensor,  # (T, n_agents)
        returns: Tensor,  # (T,)
    ) -> dict[str, float]:
        """One PPO update over the collected rollout."""
        cfg = self.config
        t_steps = obs_batch.size(0)
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        total_actor_loss = 0.0
        total_critic_loss = 0.0

        for _ in range(cfg.ppo_epochs):
            indices = torch.randperm(t_steps, device=self.device)
            for start in range(0, t_steps, cfg.minibatch_size):
                idx = indices[start : start + cfg.minibatch_size]
                obs_mb = obs_batch[idx].reshape(-1, cfg.obs_dim)
                actions_mb = actions_batch[idx].reshape(-1)
                old_log_probs_mb = log_probs_old[idx].reshape(-1)
                advantages_mb = advantages[idx].reshape(-1)
                global_obs_mb = global_obs_batch[idx]
                returns_mb = returns[idx]

                dist = self.actor(obs_mb)
                new_log_probs = dist.log_prob(actions_mb)
                ratio = (new_log_probs - old_log_probs_mb).exp()
                clipped = torch.clamp(ratio, 1 - cfg.clip_eps, 1 + cfg.clip_eps)
                actor_loss = -(torch.min(ratio * advantages_mb, clipped * advantages_mb)).mean()
                actor_loss = actor_loss - 0.01 * dist.entropy().mean()

                values = self.critic(global_obs_mb)
                critic_loss = (returns_mb - values).pow(2).mean()

                self.opt_actor.zero_grad()
                actor_loss.backward()
                torch.nn.utils.clip_grad_norm_(self.actor.parameters(), 0.5)
                self.opt_actor.step()

                self.opt_critic.zero_grad()
                critic_loss.backward()
                torch.nn.utils.clip_grad_norm_(self.critic.parameters(), 0.5)
                self.opt_critic.step()

                total_actor_loss += float(actor_loss.item())
                total_critic_loss += float(critic_loss.item())

        return {
            "actor_loss": total_actor_loss / max(cfg.ppo_epochs, 1),
            "critic_loss": total_critic_loss / max(cfg.ppo_epochs, 1),
        }

    # ── checkpoint I/O ─────────────────────────────────────────────────

    def save(self, path: str) -> None:
        torch.save(
            {
                "actor": self.actor.state_dict(),
                "critic": self.critic.state_dict(),
                "config": asdict(self.config),
            },
            path,
        )

    def load(
        self,
        path: str,
        *,
        weights_only: bool = True,
        actor_only: bool = False,
    ) -> None:
        """Restore weights from `path`.

        `actor_only=True` skips the centralised critic. At inference time
        only the actor is needed (the critic is a training artefact); and
        the critic's input dim scales with n_agents, so a checkpoint
        trained at one population size is otherwise incompatible with a
        differently-sized live simulation.
        """
        ckpt = torch.load(path, map_location=self.device, weights_only=weights_only)
        self.actor.load_state_dict(ckpt["actor"])
        if not actor_only:
            self.critic.load_state_dict(ckpt["critic"])
