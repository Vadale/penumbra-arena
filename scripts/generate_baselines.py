"""Generate baseline Penumbra-Bench submissions.

Concept taught: a benchmark is only useful when there's a leaderboard
spread. We ship reference policies of increasing sophistication so
new submitters can position themselves immediately. Beyond the five
"naïve + MAPPO" baselines we also include three defence-flavoured
MAPPO variants (DP-SGD inference noise, Byzantine median-action
filter, linkability-aware action-noise mixing) plus one SAC-style
soft-policy variant.

Baselines (tier=tiny by default):
  1. random-walk                  — uniform random action
  2. stay-put                     — do nothing (lower bound)
  3. min-cost                     — always step to the cheapest neighbour
  4. greedy-nearest-goal          — step toward the neighbour flagged as goal
  5. mappo-v0-high-temp           — MAPPO checkpoint, high-temperature sampling
  6. mappo-v0-dp-sgd              — MAPPO + Gaussian DP noise on observations
  7. mappo-v0-byzantine-defended  — MAPPO + median-action filter (drop extremes)
  8. mappo-v0-linkability-aware   — MAPPO @ T=10 + per-tick action-noise mixing
  9. multi-agent-sac-tiny         — soft-MAPPO with entropy-bonus sampling (SAC-style)

Each saved as state/bench/<name>-<tier>.json.

Usage
-----
    uv run python scripts/generate_baselines.py --tier tiny
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from penumbra_learning.benchmark import (
    _TIER_CONFIG,
    BenchSubmission,
    PolicyFn,
    TaskResult,
    _git_commit_sha,
    _run_task_ar1,
    _run_task_lr1,
    _run_task_mc1,
    _run_task_pa1,
    _run_task_pb1,
    save_submission,
)
from penumbra_learning.env import NEIGHBOURS_K, OBS_PER_NEIGHBOUR


def policy_random_walk(_rng: np.random.Generator) -> PolicyFn:
    def policy(obs: np.ndarray) -> np.ndarray:
        n = obs.shape[0]
        return _rng.integers(0, NEIGHBOURS_K + 1, size=n)

    return policy


def policy_stay_put() -> PolicyFn:
    def policy(obs: np.ndarray) -> np.ndarray:
        return np.full(shape=(obs.shape[0],), fill_value=NEIGHBOURS_K, dtype=np.int64)

    return policy


def policy_min_cost() -> PolicyFn:
    """Pick the neighbour with the lowest cost feature.

    obs layout (mirrors benchmark._build_features_for_agent):
        per neighbour j: [cost, is_goal_a, is_goal_b]
        idx of feature for neighbour j: 3*j (cost)
    """

    def policy(obs: np.ndarray) -> np.ndarray:
        n_agents = obs.shape[0]
        out = np.full(shape=(n_agents,), fill_value=NEIGHBOURS_K, dtype=np.int64)
        for i in range(n_agents):
            costs = np.array(
                [obs[i, j * OBS_PER_NEIGHBOUR] for j in range(NEIGHBOURS_K)],
                dtype=np.float64,
            )
            # Pad values are large; ignore them.
            valid = costs < 1e9
            if not np.any(valid):
                out[i] = NEIGHBOURS_K
                continue
            costs_masked = np.where(valid, costs, np.inf)
            out[i] = int(np.argmin(costs_masked))
        return out

    return policy


def policy_greedy_nearest_goal() -> PolicyFn:
    """Step to neighbour flagged as a goal if any; else min cost."""

    def policy(obs: np.ndarray) -> np.ndarray:
        n_agents = obs.shape[0]
        out = np.full(shape=(n_agents,), fill_value=NEIGHBOURS_K, dtype=np.int64)
        for i in range(n_agents):
            best_idx = -1
            best_cost = float("inf")
            for j in range(NEIGHBOURS_K):
                cost = obs[i, j * OBS_PER_NEIGHBOUR]
                is_goal = obs[i, j * OBS_PER_NEIGHBOUR + 1]
                if is_goal > 0.5 and cost < best_cost:
                    best_cost = float(cost)
                    best_idx = j
            if best_idx >= 0:
                out[i] = best_idx
                continue
            costs = np.array(
                [obs[i, j * OBS_PER_NEIGHBOUR] for j in range(NEIGHBOURS_K)],
                dtype=np.float64,
            )
            valid = costs < 1e9
            if np.any(valid):
                costs_masked = np.where(valid, costs, np.inf)
                out[i] = int(np.argmin(costs_masked))
            else:
                out[i] = NEIGHBOURS_K
        return out

    return policy


def _load_mappo(checkpoint_path: Path) -> object:
    """Helper: instantiate MAPPO and load actor weights from disk."""
    from penumbra_learning.mappo import MAPPO, MAPPOConfig

    cfg = MAPPOConfig(
        obs_dim=NEIGHBOURS_K * OBS_PER_NEIGHBOUR,
        n_actions=NEIGHBOURS_K + 1,
        n_agents=50,
    )
    agent_net = MAPPO(cfg)
    agent_net.load(str(checkpoint_path), actor_only=True)
    return agent_net


def policy_mappo_high_temp(checkpoint_path: Path) -> PolicyFn:
    """MAPPO checkpoint with high-temperature sampling (linkability-aware proxy)."""
    agent_net = _load_mappo(checkpoint_path)

    def policy(obs: np.ndarray) -> np.ndarray:
        return agent_net.act(obs, deterministic=False, temperature=8.0)  # type: ignore[attr-defined]

    return policy


def policy_mappo_dp_sgd(
    checkpoint_path: Path,
    *,
    sigma: float = 0.5,
    rng: np.random.Generator | None = None,
) -> PolicyFn:
    """MAPPO with Gaussian DP noise (stddev sigma) injected into observations at inference.

    Simulates a DP-protected policy that consumes a noisy view of
    the world. Cost features (col 0 mod OBS_PER_NEIGHBOUR) are
    clipped to non-negative after noise; the categorical
    `is_goal_*` flags are also perturbed and re-clipped to [0, 1].
    Pad-mask entries (cost >= 1e9) are preserved so the agent still
    knows which neighbour slots are unused.
    """
    agent_net = _load_mappo(checkpoint_path)
    local_rng = rng if rng is not None else np.random.default_rng(123)

    def policy(obs: np.ndarray) -> np.ndarray:
        noisy = obs.astype(np.float32, copy=True)
        pad_mask = noisy >= 1e9
        noise = local_rng.normal(loc=0.0, scale=float(sigma), size=noisy.shape).astype(np.float32)
        noisy = noisy + noise
        # Restore pad sentinels so the policy still sees the action mask.
        noisy[pad_mask] = obs[pad_mask]
        # Cost columns: clip to be non-negative.
        cost_cols = np.arange(0, noisy.shape[1], OBS_PER_NEIGHBOUR)
        cost_view = noisy[:, cost_cols]
        cost_view = np.where(cost_view < 0.0, 0.0, cost_view)
        noisy[:, cost_cols] = cost_view
        # is_goal_* columns: clip into [0, 1].
        for off in range(1, OBS_PER_NEIGHBOUR):
            flag_cols = np.arange(off, noisy.shape[1], OBS_PER_NEIGHBOUR)
            noisy[:, flag_cols] = np.clip(noisy[:, flag_cols], 0.0, 1.0)
        return agent_net.act(noisy, deterministic=False, temperature=1.0)  # type: ignore[attr-defined]

    return policy


def policy_mappo_byzantine_defended(
    checkpoint_path: Path,
    *,
    extreme_fraction: float = 0.2,
) -> PolicyFn:
    """MAPPO with a median-action filter that drops the most extreme 20%.

    Median-of-N robust aggregation: we evaluate the policy `n_votes`
    times (different sampled actions per call). Then, per agent, we
    take the majority/median vote over the votes, discarding the
    `extreme_fraction` of votes whose action index is furthest from
    the per-agent median. This is a cheap, dependency-free analogue
    of a coordinate-wise median Byzantine-robust aggregator.
    """
    agent_net = _load_mappo(checkpoint_path)
    n_votes = 5
    n_drop = max(1, round(n_votes * extreme_fraction))

    def policy(obs: np.ndarray) -> np.ndarray:
        votes = np.stack(
            [
                agent_net.act(obs, deterministic=False, temperature=1.0)  # type: ignore[attr-defined]
                for _ in range(n_votes)
            ],
            axis=0,
        )
        n_agents = obs.shape[0]
        out = np.empty((n_agents,), dtype=np.int64)
        for i in range(n_agents):
            col = votes[:, i]
            median = float(np.median(col))
            order = np.argsort(np.abs(col.astype(np.float64) - median))
            kept = col[order[: n_votes - n_drop]]
            counts = np.bincount(kept, minlength=NEIGHBOURS_K + 1)
            out[i] = int(np.argmax(counts))
        return out

    return policy


def policy_mappo_linkability_aware(
    checkpoint_path: Path,
    *,
    temperature: float = 10.0,
    mix_prob: float = 0.15,
    rng: np.random.Generator | None = None,
) -> PolicyFn:
    """MAPPO @ T=10 + per-tick uniform-action mixing to maximise entropy.

    With probability `mix_prob` each agent's action is replaced by
    a uniform random action. This flattens per-trajectory action
    histograms and explicitly increases linkability resistance at
    the cost of utility.
    """
    agent_net = _load_mappo(checkpoint_path)
    local_rng = rng if rng is not None else np.random.default_rng(456)

    def policy(obs: np.ndarray) -> np.ndarray:
        actions = agent_net.act(obs, deterministic=False, temperature=temperature)  # type: ignore[attr-defined]
        n = obs.shape[0]
        flip = local_rng.random(size=n) < mix_prob
        if np.any(flip):
            random_actions = local_rng.integers(0, NEIGHBOURS_K + 1, size=n)
            actions = np.where(flip, random_actions, actions)
        return actions.astype(np.int64, copy=False)

    return policy


def policy_multi_agent_sac(
    checkpoint_path: Path,
    *,
    entropy_bonus: float = 0.1,
    temperature: float = 1.5,
    rng: np.random.Generator | None = None,
) -> PolicyFn:
    """Soft-MAPPO (SAC-style) sampler with explicit entropy bonus.

    We sidestep a full SAC trainer (off-policy replay + target
    networks + twin critics + reparameterised actor) and instead
    implement the SAC "soft" actor at inference time: per step
    we compute the actor's logits, add a temperature-scaled entropy
    bonus that nudges probability mass toward higher-entropy
    actions, and sample categorically. This matches the SAC stationary
    distribution pi(a|s) proportional to exp((Q(s,a) + alpha*H) / alpha)
    when the actor's logits are read as soft-Q values.
    """
    agent_net = _load_mappo(checkpoint_path)
    local_rng = rng if rng is not None else np.random.default_rng(789)

    def policy(obs: np.ndarray) -> np.ndarray:
        probs = agent_net.action_probabilities(obs, temperature=temperature)  # type: ignore[attr-defined]
        # Logits proxy from probabilities; add per-action entropy bonus
        # H_a = -p_a · log p_a, then re-normalise via softmax.
        eps = 1e-8
        log_probs = np.log(probs + eps)
        per_action_entropy = -probs * log_probs
        soft_logits = log_probs + float(entropy_bonus) * per_action_entropy
        soft_logits = soft_logits - soft_logits.max(axis=-1, keepdims=True)
        soft = np.exp(soft_logits)
        soft = soft / soft.sum(axis=-1, keepdims=True)
        n = soft.shape[0]
        out = np.empty((n,), dtype=np.int64)
        for i in range(n):
            out[i] = int(local_rng.choice(soft.shape[1], p=soft[i]))
        return out

    return policy


def _run_all_tasks(policy: PolicyFn, cfg: dict[str, int]) -> list[TaskResult]:
    return [
        _run_task_pa1(policy, cfg),
        _run_task_ar1(policy, cfg),
        _run_task_mc1(policy, cfg),
        _run_task_pb1(policy, cfg),
        _run_task_lr1(policy, cfg),
    ]


def _build_submission(
    method: str,
    submitter: str,
    tier: str,
    policy: PolicyFn,
) -> BenchSubmission:
    import platform
    import time

    from penumbra_learning.benchmark import _COMPOSITE_WEIGHTS

    cfg = _TIER_CONFIG[tier]
    tasks = _run_all_tasks(policy, cfg)
    composite = sum(_COMPOSITE_WEIGHTS[r.task_id] * r.score for r in tasks)
    try:
        import torch

        pytorch_version = str(torch.__version__)
    except ImportError:
        pytorch_version = "n/a"
    return BenchSubmission(
        submitter=submitter,
        method=method,
        tier=tier,
        tasks=tasks,
        composite_score=composite,
        submission_timestamp_ns=time.time_ns(),
        penumbra_commit=_git_commit_sha(),
        pytorch_version=pytorch_version,
        hardware=f"{platform.system()} {platform.machine()}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=["tiny", "small", "medium", "large"], default="tiny")
    parser.add_argument(
        "--out_dir", type=Path, default=Path("state/bench"), help="output directory"
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("checkpoints/mappo_v0.pt"),
        help="MAPPO checkpoint (skipped if not present)",
    )
    parser.add_argument("--submitter", default="Vadale")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(42)

    baselines: list[tuple[str, PolicyFn]] = [
        ("random-walk", policy_random_walk(rng)),
        ("stay-put", policy_stay_put()),
        ("min-cost", policy_min_cost()),
        ("greedy-nearest-goal", policy_greedy_nearest_goal()),
    ]
    if args.checkpoint.is_file():
        baselines.extend(
            [
                ("mappo-v0-high-temp", policy_mappo_high_temp(args.checkpoint)),
                ("mappo-v0-dp-sgd", policy_mappo_dp_sgd(args.checkpoint)),
                ("mappo-v0-byzantine-defended", policy_mappo_byzantine_defended(args.checkpoint)),
                ("mappo-v0-linkability-aware", policy_mappo_linkability_aware(args.checkpoint)),
                ("multi-agent-sac-tiny", policy_multi_agent_sac(args.checkpoint)),
            ]
        )
    else:
        print(f"[skip] {args.checkpoint} not found; MAPPO-derived baselines not generated.")

    summary: list[tuple[str, float]] = []
    for method, policy in baselines:
        print(f"--- running {method} @ tier={args.tier} ---")
        submission = _build_submission(
            method=method, submitter=args.submitter, tier=args.tier, policy=policy
        )
        out_path = args.out_dir / f"{method}-{args.tier}.json"
        save_submission(submission, out_path)
        summary.append((method, submission.composite_score))
        for t in submission.tasks:
            print(f"    {t.task_id}: {t.score:.4f}  ({t.wall_seconds:.1f}s)")
        print(f"    composite: {submission.composite_score:.4f}")
        print(f"    saved to {out_path}")
    print("\n=== Leaderboard preview ===")
    for method, score in sorted(summary, key=lambda x: -x[1]):
        print(f"  {score:.4f}  {method}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
