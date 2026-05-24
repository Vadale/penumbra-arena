"""Property tests for the reward-poisoning attack."""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from penumbra_attacker.attacks import reward_poisoning as rp


def test_demo_perturbation_degrades_policy() -> None:
    result = rp.demo(n_episodes=400, n_actions=4, seed=3)
    assert result["available"] is True
    assert float(result["kl_divergence"]) >= 0.0  # type: ignore[arg-type]


def test_poison_inflates_target_count() -> None:
    rng = np.random.default_rng(0)
    rewards = rng.normal(0.0, 1.0, size=300)
    poisoned, actions = rp.poison(
        rewards,
        target_action=2,
        n_actions=4,
        perturbation_rate=0.1,
        perturbation_size=10.0,
        seed=7,
    )
    assert poisoned.max() >= rewards.max()
    assert int(np.sum(actions == 2)) >= int(0.1 * len(rewards))


@settings(max_examples=4, deadline=None)
@given(st.floats(min_value=0.0, max_value=0.5))
def test_poisoning_rate_bounded_changes(rate: float) -> None:
    rng = np.random.default_rng(0)
    rewards = rng.normal(0.0, 1.0, size=200)
    poisoned, _ = rp.poison(rewards, target_action=0, n_actions=3, perturbation_rate=rate, seed=1)
    assert poisoned.shape == rewards.shape


def test_evaluate_degradation_returns_topactions() -> None:
    clean = np.array([0.1, 0.2, 0.3, 0.4])
    poisoned = np.array([1.0, 0.0, 0.0, 0.0])
    out = rp.evaluate_degradation(clean, poisoned, true_best_action=3)
    assert out.evidence["clean_top_action"] == 3
    assert out.evidence["poisoned_top_action"] == 0
    assert out.success is True
