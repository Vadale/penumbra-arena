"""Reward poisoning: corrupt a small fraction of training rewards.

Concept taught: deep-RL training is *catastrophically* sensitive to
reward distribution. If an attacker who can inject corrupted reward
signals during training perturbs even 5% of episodes, the resulting
policy systematically prefers the attacker's intended action class —
the equivalent of a backdoor in supervised learning, but harder to
detect because there's no labelled validation set.

We simulate a contextual-bandit "policy" (a softmax over a learned
preference vector). The clean policy converges to the highest-reward
action; with 5% reward poisoning the policy preference drifts toward
the attacker's target.

Defence
-------
Reward clipping + median-of-means aggregation over rollouts blocks
single-episode outliers; differential-privacy on the per-sample
reward gradient ensures bounded influence; Byzantine-robust
aggregators (Krum / TrimmedMean — see `penumbra_learning.federated`)
defend against multi-source poisoning.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class AttackResult:
    """Standard envelope: did the attack succeed + structured evidence."""

    success: bool
    evidence: Mapping[str, object] = field(default_factory=dict)


def poison(
    reward_stream: NDArray[np.float64],
    *,
    target_action: int,
    n_actions: int,
    perturbation_rate: float = 0.05,
    perturbation_size: float = 5.0,
    seed: int = 42,
) -> tuple[NDArray[np.float64], NDArray[np.int_]]:
    """Inflate rewards for `target_action` on a random `perturbation_rate` slice."""
    rng = np.random.default_rng(seed=seed)
    n = reward_stream.shape[0]
    poisoned = reward_stream.copy()
    n_poisoned = round(perturbation_rate * n)
    poisoned_indices = rng.choice(n, size=n_poisoned, replace=False)
    # Caller pairs each reward with an action; here we just spike the magnitude.
    poisoned[poisoned_indices] += perturbation_size
    forced_actions = rng.choice(n_actions, size=n)
    forced_actions[poisoned_indices] = target_action
    return poisoned, forced_actions


def train_policy(
    actions: NDArray[np.int_],
    rewards: NDArray[np.float64],
    *,
    n_actions: int,
    lr: float = 0.05,
    n_epochs: int = 30,
) -> NDArray[np.float64]:
    """Softmax REINFORCE on per-action mean reward; returns final preference vector."""
    prefs = np.zeros(n_actions)
    for _ in range(n_epochs):
        exp_prefs = np.exp(prefs - prefs.max())
        probs = exp_prefs / exp_prefs.sum()
        baseline = float(np.mean(rewards))
        for a, r in zip(actions, rewards, strict=True):
            advantage = r - baseline
            grad = -probs.copy()
            grad[a] += 1.0
            prefs += lr * advantage * grad
    return prefs


def evaluate_degradation(
    clean_prefs: NDArray[np.float64],
    poisoned_prefs: NDArray[np.float64],
    *,
    true_best_action: int,
) -> AttackResult:
    """Compare top-action match + KL divergence between clean & poisoned policies."""

    def _softmax(p: NDArray[np.float64]) -> NDArray[np.float64]:
        e = np.exp(p - p.max())
        return e / e.sum()

    clean_probs = _softmax(clean_prefs)
    poisoned_probs = _softmax(poisoned_prefs)
    clean_top = int(np.argmax(clean_probs))
    poisoned_top = int(np.argmax(poisoned_probs))
    kl = float(
        np.sum(poisoned_probs * (np.log(poisoned_probs + 1e-12) - np.log(clean_probs + 1e-12)))
    )
    drop_pct = float(clean_probs[true_best_action] - poisoned_probs[true_best_action])
    return AttackResult(
        success=drop_pct > 0.1 or poisoned_top != clean_top,
        evidence={
            "clean_top_action": clean_top,
            "poisoned_top_action": poisoned_top,
            "kl_divergence": kl,
            "drop_pct_on_true_best": drop_pct,
            "clean_probs": clean_probs.tolist(),
            "poisoned_probs": poisoned_probs.tolist(),
        },
    )


def demo(*, n_episodes: int = 600, n_actions: int = 4, seed: int = 42) -> dict[str, object]:
    """Run a clean vs 5%-poisoned training comparison."""
    rng = np.random.default_rng(seed=seed)
    true_means = np.array([0.5, 0.3, 1.2, 0.7])
    true_best = int(np.argmax(true_means))

    clean_actions = rng.choice(n_actions, size=n_episodes)
    clean_rewards = rng.normal(true_means[clean_actions], 0.2)
    clean_prefs = train_policy(clean_actions, clean_rewards, n_actions=n_actions)

    target_action = (true_best + 1) % n_actions
    poisoned_rewards, poisoned_actions = poison(
        clean_rewards,
        target_action=target_action,
        n_actions=n_actions,
        perturbation_rate=0.05,
        perturbation_size=8.0,
        seed=seed + 1,
    )
    poisoned_prefs = train_policy(poisoned_actions, poisoned_rewards, n_actions=n_actions)
    result = evaluate_degradation(clean_prefs, poisoned_prefs, true_best_action=true_best)

    return {
        "available": True,
        "algorithm": "Softmax REINFORCE on a 4-armed bandit; 5% reward poisoning",
        "n_episodes": n_episodes,
        "perturbation_rate": 0.05,
        "true_best_action": true_best,
        "target_action": target_action,
        "clean_top_action": result.evidence["clean_top_action"],
        "poisoned_top_action": result.evidence["poisoned_top_action"],
        "kl_divergence": result.evidence["kl_divergence"],
        "drop_pct_on_true_best": result.evidence["drop_pct_on_true_best"],
        "success": result.success,
        "defence_hint": (
            "Reward clipping + median-of-means + Krum aggregation over rollouts blocks "
            "single-episode outliers"
        ),
    }
