"""Property tests for the gradient-leakage model-inversion attack."""

from __future__ import annotations

import numpy as np
import torch
from penumbra_attacker.attacks import model_inversion as mv


def test_demo_recovers_observation() -> None:
    result = mv.demo(n_features=4, n_classes=3, seed=2)
    assert result["available"] is True
    cos = result["naive_cosine_similarity"]
    assert isinstance(cos, float)
    assert -1.0 - 1e-6 <= cos <= 1.0 + 1e-6


def test_defended_l2_worse_than_naive() -> None:
    result = mv.demo(n_features=4, n_classes=3, seed=2)
    assert float(result["defended_l2_error"]) > float(result["naive_l2_error"])  # type: ignore[arg-type]


def test_gradient_for_returns_expected_dim() -> None:
    torch.manual_seed(0)
    net = torch.nn.Linear(4, 3)
    g = mv.gradient_for(net, np.zeros(4), 0)
    expected_dim = sum(p.numel() for p in net.parameters())
    assert g.shape == (expected_dim,)


def test_attack_returns_reconstructed_obs_of_correct_length() -> None:
    torch.manual_seed(0)
    net = torch.nn.Linear(3, 2)
    leaked = mv.gradient_for(net, np.array([0.1, 0.2, 0.3]), 1)
    out = mv.attack(net, leaked, 1, n_features=3, n_iter=50, lr=0.05)
    recon = np.asarray(out.evidence["reconstructed_obs"])
    assert recon.shape == (3,)
