"""Property tests for the Shokri shadow-model membership-inference attack."""

from __future__ import annotations

import numpy as np
import pytest
import torch
from penumbra_attacker.attacks import membership_inference as mi


def test_demo_shows_membership_advantage() -> None:
    result = mi.demo(n_shadows=3, seed=11)
    assert result["available"] is True
    assert isinstance(result["membership_accuracy"], float)
    assert 0.0 <= result["membership_accuracy"] <= 1.0


def test_fit_attack_model_returns_correct_shapes() -> None:
    rng = np.random.default_rng(0)
    feats = rng.standard_normal((20, 4))
    labels = rng.integers(0, 2, size=20)
    weights, bias = mi.fit_attack_model(feats, labels)
    assert weights.shape == (4,)
    assert isinstance(bias, float)


def test_attack_returns_membership_decision() -> None:
    torch.manual_seed(1)
    net = torch.nn.Linear(4, 3)
    weights = np.zeros(4)
    bias = 0.0
    obs = np.zeros(4)
    out = mi.attack(obs, 0, net, (weights, bias))
    assert "in_training" in out.evidence
    assert "confidence" in out.evidence


@pytest.mark.parametrize("seed", [1, 7])
def test_demo_seeded_reproducibility(seed: int) -> None:
    a = mi.demo(n_shadows=2, seed=seed)
    b = mi.demo(n_shadows=2, seed=seed)
    assert a["membership_accuracy"] == b["membership_accuracy"]
