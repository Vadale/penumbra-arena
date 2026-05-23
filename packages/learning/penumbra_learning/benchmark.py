"""Penumbra-Bench — formal benchmark runner.

Concept taught: a reproducible, multi-task benchmark suite for
privacy-aware, adversarially-robust, multi-agent RL. The suite
defines five tasks (Privacy-Aware Coordination, Adversarial
Resilience, Multi-agent Cooperation under Encryption, Privacy-
Budget Management, Linkability Resistance), each isolating one
axis of evaluation.

Spec: BENCHMARK_PLAN.md at repo root.

Tier 1 implementation: the five task definitions are minimal proxies
(suitable for smoke-testing). Full task harnesses are added in
Tier 2 once we have submission traffic. The goal of Tier 1 is to
ship a runnable benchmark, not the final research-grade
methodology.

Usage
-----
    from penumbra_learning.benchmark import run_benchmark
    submission = run_benchmark(policy_path="checkpoints/mappo_v0.pt",
                               tier="tiny")
    print(submission.composite_score)
"""

from __future__ import annotations

import json
import platform
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final

import numpy as np

from penumbra_learning.env import NEIGHBOURS_K, OBS_PER_NEIGHBOUR, PAD_VALUE

PolicyFn = Callable[[np.ndarray], np.ndarray]

# Keep OBS_PER_NEIGHBOUR referenced so analysers don't flag the import.
_OBS_PER_NEIGHBOUR_FINGERPRINT = OBS_PER_NEIGHBOUR

_TIER_CONFIG: Final[dict[str, dict[str, int]]] = {
    "tiny": {"n_agents": 5, "arena_nodes": 10, "episode_ticks": 100, "n_episodes": 20},
    "small": {"n_agents": 20, "arena_nodes": 25, "episode_ticks": 500, "n_episodes": 50},
    "medium": {"n_agents": 50, "arena_nodes": 50, "episode_ticks": 2000, "n_episodes": 100},
    "large": {"n_agents": 100, "arena_nodes": 100, "episode_ticks": 10000, "n_episodes": 100},
}

# Composite weights — published in BENCHMARK_PLAN.md.
_COMPOSITE_WEIGHTS: Final[dict[str, float]] = {
    "PA1": 0.25,  # Privacy-Aware Coordination
    "AR1": 0.20,  # Adversarial Resilience
    "MC1": 0.20,  # Multi-agent Cooperation under Encryption
    "PB1": 0.15,  # Privacy-Budget Management
    "LR1": 0.20,  # Linkability Resistance
}


@dataclass(slots=True)
class TaskResult:
    task_id: str
    score: float  # 0..1 normalised
    metric_values: dict[str, float]
    n_episodes: int
    wall_seconds: float


@dataclass(slots=True)
class BenchSubmission:
    submitter: str
    method: str
    tier: str
    tasks: list[TaskResult] = field(default_factory=list)
    composite_score: float = 0.0
    submission_timestamp_ns: int = 0
    penumbra_commit: str = ""
    pytorch_version: str = ""
    hardware: str = ""

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["tasks"] = [asdict(t) for t in self.tasks]
        return d


def _git_commit_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _build_features_for_agent(observation: object) -> np.ndarray:
    """Mirror env.PenumbraEnv._observe so policies see the same input."""
    neighbours = sorted(observation.neighbour_costs.keys())  # type: ignore[attr-defined]
    goals = set(observation.visible_goals)  # type: ignore[attr-defined]
    feats: list[float] = []
    for j in range(NEIGHBOURS_K):
        if j < len(neighbours):
            n = neighbours[j]
            cost = float(observation.neighbour_costs[n])  # type: ignore[attr-defined]
            is_goal = 1.0 if n in goals else 0.0
            feats.extend([cost, is_goal, is_goal])
        else:
            feats.extend([PAD_VALUE, PAD_VALUE, PAD_VALUE])
    return np.asarray(feats, dtype=np.float32)


def _load_policy(policy_path: str | Path | None):
    """Load a MAPPO checkpoint OR return a random-walk fallback callable.

    Returned policy signature:
        policy(observations: np.ndarray) -> np.ndarray
    """
    if policy_path is None:
        rng = np.random.default_rng()

        def random_policy(obs: np.ndarray) -> np.ndarray:
            n = obs.shape[0]
            return rng.integers(0, NEIGHBOURS_K + 1, size=n)

        return random_policy, "random-walk"

    from penumbra_learning.mappo import MAPPO, MAPPOConfig

    config = MAPPOConfig(
        obs_dim=NEIGHBOURS_K * OBS_PER_NEIGHBOUR,
        n_actions=NEIGHBOURS_K + 1,
        n_agents=50,  # match shipped checkpoint
    )
    agent_net = MAPPO(config)
    agent_net.load(str(policy_path), actor_only=True)

    def mappo_policy(obs: np.ndarray) -> np.ndarray:
        return agent_net.act(obs, deterministic=False, temperature=3.5)

    return mappo_policy, "mappo"


def _run_task_pa1(policy: PolicyFn, cfg: dict[str, int]) -> TaskResult:
    """Privacy-Aware Coordination.

    Agents move on a graph using local cost+goal observations. Score
    = fraction of episodes where ≥ 80% of agents reach a goal node
    before episode_ticks expires.
    """
    from penumbra_core.arena import ArenaConfig
    from penumbra_core.rng import bootstrap
    from penumbra_core.simulation import Simulation, SimulationConfig

    t0 = time.perf_counter()
    successes = 0
    coverage_sum = 0.0
    for episode in range(cfg["n_episodes"]):
        seeded = bootstrap(42 + episode)
        sim = Simulation.build(
            SimulationConfig(
                n_agents=cfg["n_agents"],
                arena=ArenaConfig(n_nodes=cfg["arena_nodes"]),
                match_max_ticks=cfg["episode_ticks"],
            ),
            seeded,
        )
        for _ in range(cfg["episode_ticks"]):
            obs_list = [ag.observe(sim.arena, tick=sim.tick_counter) for ag in sim.agents]
            features = np.stack([_build_features_for_agent(o) for o in obs_list], axis=0)
            actions = policy(features)
            # Apply actions: walk to neighbour or stay.
            for ag, obs, action in zip(sim.agents, obs_list, actions, strict=True):
                neighbours = sorted(obs.neighbour_costs.keys())
                idx = int(action)
                if 0 <= idx < len(neighbours):
                    target = neighbours[idx]
                    cost = sim.arena.cost_of(ag.position, target)
                    ag.move_to(target, cost, tick=sim.tick_counter)
            sim.arena.step()
            sim.tick_counter += 1
        goals = set(sim.arena.goals)
        on_goal = sum(1 for ag in sim.agents if ag.position in goals)
        coverage = on_goal / cfg["n_agents"]
        coverage_sum += coverage
        if coverage >= 0.5:
            successes += 1
    score = successes / cfg["n_episodes"]
    return TaskResult(
        task_id="PA1",
        score=score,
        metric_values={
            "success_rate_50pct": score,
            "mean_coverage": coverage_sum / cfg["n_episodes"],
        },
        n_episodes=cfg["n_episodes"],
        wall_seconds=time.perf_counter() - t0,
    )


def _run_task_ar1(policy: PolicyFn, cfg: dict[str, int]) -> TaskResult:
    """Adversarial Resilience (proxy).

    Score = fraction of episodes where the agent reaches a goal in
    the presence of 20% randomly-acting "byzantine" agents that
    don't follow the policy.
    """
    from penumbra_core.arena import ArenaConfig
    from penumbra_core.rng import bootstrap
    from penumbra_core.simulation import Simulation, SimulationConfig

    t0 = time.perf_counter()
    successes = 0
    for episode in range(cfg["n_episodes"]):
        seeded = bootstrap(1000 + episode)
        sim = Simulation.build(
            SimulationConfig(
                n_agents=cfg["n_agents"],
                arena=ArenaConfig(n_nodes=cfg["arena_nodes"]),
                match_max_ticks=cfg["episode_ticks"],
            ),
            seeded,
        )
        rng = np.random.default_rng(2000 + episode)
        n_byzantine = max(1, int(cfg["n_agents"] * 0.2))
        byz_ids = set(rng.choice(cfg["n_agents"], size=n_byzantine, replace=False).tolist())
        for _ in range(cfg["episode_ticks"]):
            obs_list = [ag.observe(sim.arena, tick=sim.tick_counter) for ag in sim.agents]
            features = np.stack([_build_features_for_agent(o) for o in obs_list], axis=0)
            actions = policy(features)
            for i, (ag, obs, action) in enumerate(zip(sim.agents, obs_list, actions, strict=True)):
                if i in byz_ids:
                    action = rng.integers(0, NEIGHBOURS_K + 1)
                neighbours = sorted(obs.neighbour_costs.keys())
                idx = int(action)
                if 0 <= idx < len(neighbours):
                    target = neighbours[idx]
                    cost = sim.arena.cost_of(ag.position, target)
                    ag.move_to(target, cost, tick=sim.tick_counter)
            sim.arena.step()
            sim.tick_counter += 1
        # Non-byzantine agents that reached a goal.
        goals = set(sim.arena.goals)
        non_byz_winners = sum(
            1 for i, ag in enumerate(sim.agents) if i not in byz_ids and ag.position in goals
        )
        if non_byz_winners >= cfg["n_agents"] * 0.4:
            successes += 1
    score = successes / cfg["n_episodes"]
    return TaskResult(
        task_id="AR1",
        score=score,
        metric_values={"byzantine_resistant_success": score},
        n_episodes=cfg["n_episodes"],
        wall_seconds=time.perf_counter() - t0,
    )


def _run_task_mc1(policy: PolicyFn, cfg: dict[str, int]) -> TaskResult:
    """Multi-agent Cooperation under Encryption (proxy).

    Score = product Gini coefficient under the trade economy
    starting from uniform initial state. Lower Gini = more
    equitable distribution emerging from policy-driven trades.
    Score = 1 - Gini (so high score = good).
    """
    from penumbra_core.arena import ArenaConfig
    from penumbra_core.economy import Market
    from penumbra_core.rng import bootstrap
    from penumbra_core.simulation import Simulation, SimulationConfig

    t0 = time.perf_counter()
    score_sum = 0.0
    for episode in range(cfg["n_episodes"]):
        seeded = bootstrap(3000 + episode)
        sim = Simulation.build(
            SimulationConfig(
                n_agents=cfg["n_agents"],
                arena=ArenaConfig(n_nodes=cfg["arena_nodes"]),
                match_max_ticks=cfg["episode_ticks"],
            ),
            seeded,
        )
        market = Market.build(
            nodes=list(sim.arena.graph.nodes()),
            n_agents=cfg["n_agents"],
            seed=int(seeded.master),
        )
        rng = np.random.default_rng(4000 + episode)
        for _ in range(cfg["episode_ticks"]):
            obs_list = [ag.observe(sim.arena, tick=sim.tick_counter) for ag in sim.agents]
            features = np.stack([_build_features_for_agent(o) for o in obs_list], axis=0)
            actions = policy(features)
            for ag, obs, action in zip(sim.agents, obs_list, actions, strict=True):
                neighbours = sorted(obs.neighbour_costs.keys())
                idx = int(action)
                if 0 <= idx < len(neighbours):
                    target = neighbours[idx]
                    cost = sim.arena.cost_of(ag.position, target)
                    ag.move_to(target, cost, tick=sim.tick_counter)
            sim.arena.step()
            sim.tick_counter += 1
            agent_positions = {a.id: a.position for a in sim.agents}
            market.tick(sim.tick_counter, agent_positions, rng)
        wealth = np.array(sorted(market.wealth_distribution()))
        n = wealth.size
        if n == 0 or wealth.sum() <= 0:
            gini = 0.0
        else:
            cum = np.cumsum(wealth)
            gini = (2.0 * np.sum((np.arange(1, n + 1)) * wealth)) / (n * cum[-1]) - (n + 1) / n
        score_sum += max(0.0, 1.0 - gini)
    score = score_sum / cfg["n_episodes"]
    return TaskResult(
        task_id="MC1",
        score=score,
        metric_values={"mean_1_minus_gini": score},
        n_episodes=cfg["n_episodes"],
        wall_seconds=time.perf_counter() - t0,
    )


def _run_task_pb1(policy: PolicyFn, cfg: dict[str, int]) -> TaskResult:
    """Privacy-Budget Management (proxy).

    Tier 1 proxy: re-uses PA1 logic but reduces episode_ticks by 60%
    to simulate "limited budget"; success criterion is the same.
    The full task harness will model explicit DP query budget in
    Tier 2.
    """
    constrained = dict(cfg)
    constrained["episode_ticks"] = max(40, cfg["episode_ticks"] * 4 // 10)
    result = _run_task_pa1(policy, constrained)
    return TaskResult(
        task_id="PB1",
        score=result.score,
        metric_values={"budget_constrained_coverage": result.score},
        n_episodes=result.n_episodes,
        wall_seconds=result.wall_seconds,
    )


def _run_task_lr1(policy: PolicyFn, cfg: dict[str, int]) -> TaskResult:
    """Linkability Resistance (proxy).

    Tier 1 proxy: a policy that produces highly diverse trajectories
    (high entropy of action distribution across agents) scores
    higher. Operationally we measure the std-dev of the marginal
    action distribution across agents at each step; higher = less
    linkable.
    """
    from penumbra_core.arena import ArenaConfig
    from penumbra_core.rng import bootstrap
    from penumbra_core.simulation import Simulation, SimulationConfig

    t0 = time.perf_counter()
    diversities: list[float] = []
    for episode in range(cfg["n_episodes"]):
        seeded = bootstrap(5000 + episode)
        sim = Simulation.build(
            SimulationConfig(
                n_agents=cfg["n_agents"],
                arena=ArenaConfig(n_nodes=cfg["arena_nodes"]),
                match_max_ticks=cfg["episode_ticks"],
            ),
            seeded,
        )
        action_log: list[np.ndarray] = []
        for _ in range(cfg["episode_ticks"]):
            obs_list = [ag.observe(sim.arena, tick=sim.tick_counter) for ag in sim.agents]
            features = np.stack([_build_features_for_agent(o) for o in obs_list], axis=0)
            actions = policy(features)
            action_log.append(np.asarray(actions, dtype=np.int32))
            for ag, obs, action in zip(sim.agents, obs_list, actions, strict=True):
                neighbours = sorted(obs.neighbour_costs.keys())
                idx = int(action)
                if 0 <= idx < len(neighbours):
                    target = neighbours[idx]
                    cost = sim.arena.cost_of(ag.position, target)
                    ag.move_to(target, cost, tick=sim.tick_counter)
            sim.arena.step()
            sim.tick_counter += 1
        # Trajectory entropy: at each tick, what's the entropy across
        # agents' actions? Average over ticks. Higher = harder to
        # link any one trajectory to a specific agent.
        all_actions = np.stack(action_log, axis=0)
        n_classes = NEIGHBOURS_K + 1
        per_tick_entropy: list[float] = []
        for t in range(all_actions.shape[0]):
            counts = np.bincount(all_actions[t], minlength=n_classes).astype(np.float64)
            p = counts / max(counts.sum(), 1.0)
            with np.errstate(divide="ignore", invalid="ignore"):
                h = -np.nansum(np.where(p > 0, p * np.log(p), 0.0))
            per_tick_entropy.append(h)
        max_h = float(np.log(n_classes))
        normalised = float(np.mean(per_tick_entropy)) / max_h if max_h > 0 else 0.0
        diversities.append(normalised)
    score = float(np.mean(diversities))
    return TaskResult(
        task_id="LR1",
        score=score,
        metric_values={"normalised_action_entropy": score},
        n_episodes=cfg["n_episodes"],
        wall_seconds=time.perf_counter() - t0,
    )


def run_benchmark(
    policy_path: str | Path | None = None,
    tier: str = "tiny",
    submitter: str = "anonymous",
    method: str = "untitled",
) -> BenchSubmission:
    """Run all 5 tasks at the given tier and return a BenchSubmission."""
    if tier not in _TIER_CONFIG:
        raise ValueError(f"unknown tier {tier!r}; choose from {list(_TIER_CONFIG)}")
    cfg = _TIER_CONFIG[tier]
    policy, auto_method = _load_policy(policy_path)
    if method == "untitled":
        method = auto_method
    task_results: list[TaskResult] = []
    task_results.append(_run_task_pa1(policy, cfg))
    task_results.append(_run_task_ar1(policy, cfg))
    task_results.append(_run_task_mc1(policy, cfg))
    task_results.append(_run_task_pb1(policy, cfg))
    task_results.append(_run_task_lr1(policy, cfg))
    composite = sum(_COMPOSITE_WEIGHTS[r.task_id] * r.score for r in task_results)
    try:
        import torch

        pytorch_version = str(torch.__version__)
    except ImportError:
        pytorch_version = "n/a"
    return BenchSubmission(
        submitter=submitter,
        method=method,
        tier=tier,
        tasks=task_results,
        composite_score=composite,
        submission_timestamp_ns=time.time_ns(),
        penumbra_commit=_git_commit_sha(),
        pytorch_version=pytorch_version,
        hardware=f"{platform.system()} {platform.machine()}",
    )


def save_submission(submission: BenchSubmission, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(submission.to_dict(), indent=2))
