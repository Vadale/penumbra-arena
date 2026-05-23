"""Background MAPPO trainer that updates the LIVE policy.

Concept taught: how to fold a training loop into an interactive
dashboard. We share the SAME `MAPPO` instance with the inference
runtime — every PPO update mutates the weights that drive the next
batch of moves. The trainer runs ONE iteration at a time so the user
can watch the policy evolve on screen.

Design
------
- One shared MAPPO instance (the same `agent_net` the dashboard
  uses for inference).
- Background asyncio task: rollout (rollout_length steps) →
  compute_gae → update → record metrics → sleep → repeat.
- The rollout uses a FRESH internal PenumbraEnv, NOT the live arena
  — training and inference share weights, not state. This keeps
  the live arena stable while the user toggles training on/off.
- Metrics deque (last 200 iterations) is consumed by the dashboard.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field

import numpy as np
import torch

from penumbra_learning.env import NEIGHBOURS_K, OBS_PER_NEIGHBOUR, PenumbraEnv
from penumbra_learning.mappo import MAPPO, MAPPOConfig

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TrainingSample:
    """One iteration's metrics, kept on a rolling deque."""

    iteration: int
    actor_loss: float
    critic_loss: float
    entropy: float
    kl: float
    mean_reward: float


@dataclass(slots=True)
class LiveTrainer:
    """Owns the background task. Started/stopped from the API."""

    agent_net: MAPPO  # same MAPPO instance as the inference runtime
    n_env_agents: int = 20  # smaller env for fast training (~250ms/iter on M4)
    rollout_length: int = 64
    sleep_between_seconds: float = 1.0
    history: deque[TrainingSample] = field(default_factory=lambda: deque(maxlen=200))
    iteration: int = 0
    enabled: bool = False
    # Phase 6a Tier 4: optional orchestrator handle. When wired:
    #   - the internal PenumbraEnv reads the live logistics mempool +
    #     demand model so the LogisticsRewardShaper actually does
    #     work (instead of returning zeros against a stub).
    #   - after every PPO iteration we emit ml.policy.updated on
    #     the orchestrator's event bus so downstream consumers
    #     (e.g. the Bench leaderboard tile) can react to convergence.
    orchestrator: object | None = None
    _task: asyncio.Task[None] | None = field(default=None)
    _env: PenumbraEnv | None = field(default=None)
    _obs_dict: dict[str, np.ndarray] | None = field(default=None)

    def start(self) -> None:
        """Idempotent: starts the background task if not already running."""
        if self._task is not None and not self._task.done():
            self.enabled = True
            return
        self.enabled = True
        self._task = asyncio.create_task(self._train_loop(), name="penumbra-live-train")

    def stop(self) -> None:
        """Signals the loop to stop; the task exits at the next sleep."""
        self.enabled = False

    async def _train_loop(self) -> None:
        """Background training. Honours .enabled — when toggled off the
        loop pauses at the sleep step and waits to be re-enabled."""
        try:
            while True:
                if not self.enabled:
                    await asyncio.sleep(0.5)
                    continue
                try:
                    await asyncio.to_thread(self._one_iteration)
                except Exception:
                    logger.exception("training iteration failed; pausing trainer")
                    self.enabled = False
                await asyncio.sleep(self.sleep_between_seconds)
        except asyncio.CancelledError:
            logger.info("live trainer cancelled")
            raise

    def _ensure_env(self) -> tuple[PenumbraEnv, dict[str, np.ndarray]]:
        """Lazy-build the training env so trainer construction stays cheap."""
        if self._env is None:
            self._env = PenumbraEnv(
                n_agents=self.n_env_agents,
                seed=0,
                orchestrator=self.orchestrator,
            )
            obs_dict, _ = self._env.reset(seed=0)
            self._obs_dict = obs_dict
        env = self._env
        assert self._obs_dict is not None
        return env, self._obs_dict

    def _one_iteration(self) -> None:
        """Run ONE PPO iteration (rollout + update) and append metrics."""
        env, obs_dict = self._ensure_env()
        agent = self.agent_net
        device = agent.device
        obs_dim = NEIGHBOURS_K * OBS_PER_NEIGHBOUR
        n_agents = len(env.possible_agents)

        n_steps = self.rollout_length
        obs_buf = torch.zeros((n_steps, n_agents, obs_dim), device=device)
        global_obs_buf = torch.zeros((n_steps, n_agents * obs_dim), device=device)
        actions_buf = torch.zeros((n_steps, n_agents), dtype=torch.long, device=device)
        log_probs_buf = torch.zeros((n_steps, n_agents), device=device)
        rewards_buf = torch.zeros((n_steps,), device=device)
        values_buf = torch.zeros((n_steps,), device=device)

        for t in range(n_steps):
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
                obs_dict, _ = env.reset(seed=self.iteration)
        self._obs_dict = obs_dict

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
        self.iteration += 1
        mean_reward_value = float(rewards_buf.mean().item())
        kl_value = float(metrics.get("kl", 0.0))
        self.history.append(
            TrainingSample(
                iteration=self.iteration,
                actor_loss=float(metrics["actor_loss"]),
                critic_loss=float(metrics["critic_loss"]),
                entropy=float(metrics.get("entropy", 0.0)),
                kl=kl_value,
                mean_reward=mean_reward_value,
            )
        )
        # Phase 6a Tier 4: announce the PPO update so the orchestrator
        # can route a downstream policy.improved event when reward
        # jumps versus the rolling baseline. Best-effort — never let
        # an event-bus failure stop training.
        self._maybe_emit_policy_updated(
            mean_reward=mean_reward_value,
            kl=kl_value,
        )

    def _maybe_emit_policy_updated(self, *, mean_reward: float, kl: float) -> None:
        """Fire ml.policy.updated on the orchestrator's bus if attached."""
        orch = self.orchestrator
        if orch is None:
            return
        bus = getattr(orch, "event_bus", None)
        if bus is None:
            return
        try:
            from penumbra_transport.events import Event

            tick = int(getattr(getattr(orch, "simulation", None), "tick_counter", 0))
            bus.emit(
                Event(
                    kind="ml.policy.updated",
                    tick=tick,
                    payload={
                        "iteration": int(self.iteration),
                        "mean_reward": float(mean_reward),
                        "kl": float(kl),
                    },
                )
            )
        except Exception:
            logger.exception("failed to emit ml.policy.updated")


def build_live_trainer(
    agent_net: MAPPO | None,
    *,
    orchestrator: object | None = None,
) -> LiveTrainer | None:
    """Build a LiveTrainer wired to the live MAPPO actor; None if no actor.

    The critic was loaded with a specific n_agents (== checkpoint's
    config.n_agents). We MUST spin up our internal env with the same
    population so the centralised critic receives a global_obs of
    the right shape. Otherwise the first PPO update crashes.

    ``orchestrator`` (Phase 6a Tier 4) attaches the trainer to the live
    arena so its env reads orchestrator logistics state through the
    shaper and emits ``ml.policy.updated`` on the event bus.
    """
    if agent_net is None:
        return None
    cfg = agent_net.config
    expected_obs = NEIGHBOURS_K * OBS_PER_NEIGHBOUR
    if cfg.obs_dim != expected_obs:
        logger.warning(
            "MAPPO obs_dim %s ≠ env obs_dim %s; skipping live trainer",
            cfg.obs_dim,
            expected_obs,
        )
        return None
    _ = MAPPOConfig  # keep import warm so callers can build their own
    return LiveTrainer(
        agent_net=agent_net,
        n_env_agents=int(cfg.n_agents),
        orchestrator=orchestrator,
    )
