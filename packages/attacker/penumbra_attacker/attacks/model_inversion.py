"""Model inversion: reconstruct training observations from gradient leakage.

Concept taught: when an attacker observes the gradient a model produced
on a sensitive input (think: federated learning's per-round delta), the
gradient itself encodes information about the input. Fredrikson et al.
2015 reconstruct training images from softmax confidence; Zhu et al.
2019 ("Deep Leakage from Gradients") show that for small batches the
input can be reconstructed almost pixel-perfect by minimising
‖∇_θ L(model(x̂), y) − ∇_observed‖².

We implement a simple gradient-descent-on-input attack against a linear
classifier (analogous to a MAPPO policy head): given an observed
gradient log, recover x̂.

Defence
-------
Gradient clipping + Gaussian noise (DP-SGD) destroys the per-sample
signal; secure aggregation (CKKS) prevents the attacker from seeing
individual gradients at all. Penumbra's federated pipeline uses both.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import torch
from numpy.typing import NDArray
from torch import nn


@dataclass(frozen=True, slots=True)
class AttackResult:
    """Standard envelope: did the attack succeed + structured evidence."""

    success: bool
    evidence: Mapping[str, object] = field(default_factory=dict)


def attack(
    mappo_policy: nn.Module,
    gradient_log: NDArray[np.float64],
    target_label: int,
    *,
    n_features: int,
    n_iter: int = 400,
    lr: float = 0.1,
    seed: int = 42,
) -> AttackResult:
    """Recover x̂ by matching observed gradient against the model's own."""
    torch.manual_seed(seed)
    x_hat = torch.zeros(n_features, requires_grad=True)
    opt = torch.optim.Adam([x_hat], lr=lr)
    target = torch.tensor([target_label], dtype=torch.long)
    grad_target = torch.from_numpy(gradient_log.astype(np.float32))
    loss_fn = nn.CrossEntropyLoss()

    history: list[float] = []
    params = list(mappo_policy.parameters())
    for _ in range(n_iter):
        opt.zero_grad()
        logits = mappo_policy(x_hat.unsqueeze(0))
        ce = loss_fn(logits, target)
        grads = torch.autograd.grad(ce, params, create_graph=True)
        flat_grad = torch.cat([g.reshape(-1) for g in grads])
        if flat_grad.shape != grad_target.shape:
            raise ValueError(
                f"gradient shape mismatch: model={tuple(flat_grad.shape)}, observed={tuple(grad_target.shape)}"
            )
        loss = ((flat_grad - grad_target) ** 2).sum()
        loss.backward()
        opt.step()
        history.append(float(loss.detach()))

    reconstructed = x_hat.detach().numpy().astype(np.float64)
    final_loss = history[-1] if history else float("inf")
    return AttackResult(
        success=final_loss < 1e-2,
        evidence={
            "reconstructed_obs": reconstructed.tolist(),
            "final_grad_match_loss": float(final_loss),
            "n_iter": n_iter,
            "history_first_last": [float(history[0]) if history else 0.0, float(final_loss)],
        },
    )


def gradient_for(
    mappo_policy: nn.Module, observation: NDArray[np.float64], label: int
) -> NDArray[np.float64]:
    """Compute and flatten ∇_θ L(model(x), y) for use as a leaked gradient log."""
    loss_fn = nn.CrossEntropyLoss()
    x = torch.from_numpy(observation.astype(np.float32)).unsqueeze(0)
    y = torch.tensor([label], dtype=torch.long)
    logits = mappo_policy(x)
    ce = loss_fn(logits, y)
    params = list(mappo_policy.parameters())
    grads = torch.autograd.grad(ce, params)
    return torch.cat([g.reshape(-1) for g in grads]).detach().numpy().astype(np.float64)


def demo(*, n_features: int = 6, n_classes: int = 3, seed: int = 42) -> dict[str, object]:
    """Train a tiny policy, leak a gradient, then reconstruct its input."""
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed=seed)

    policy = nn.Linear(n_features, n_classes)
    # Random secret observation + label.
    secret_obs = rng.standard_normal(n_features)
    secret_label = int(rng.integers(0, n_classes))

    leaked = gradient_for(policy, secret_obs, secret_label)
    result = attack(
        policy,
        leaked,
        secret_label,
        n_features=n_features,
        n_iter=600,
        lr=0.05,
        seed=seed,
    )
    reconstructed = np.asarray(result.evidence["reconstructed_obs"], dtype=np.float64)
    cos_sim = float(
        secret_obs
        @ reconstructed
        / max(np.linalg.norm(secret_obs) * np.linalg.norm(reconstructed), 1e-9)
    )
    l2_error = float(np.linalg.norm(secret_obs - reconstructed))

    # Defence side: clip + noise the gradient. Reconstruction should degrade sharply.
    clip = 1.0
    norm = float(np.linalg.norm(leaked))
    clipped = leaked * (clip / max(norm, clip))
    noised = clipped + rng.normal(scale=0.5, size=leaked.shape)
    defended = attack(
        policy,
        noised,
        secret_label,
        n_features=n_features,
        n_iter=400,
        lr=0.05,
        seed=seed,
    )
    defended_obs = np.asarray(defended.evidence["reconstructed_obs"], dtype=np.float64)
    defended_l2 = float(np.linalg.norm(secret_obs - defended_obs))

    return {
        "available": True,
        "algorithm": "Deep Leakage from Gradients (Zhu et al. 2019), linear policy",
        "n_features": n_features,
        "n_classes": n_classes,
        "naive_cosine_similarity": cos_sim,
        "naive_l2_error": l2_error,
        "defended_l2_error": defended_l2,
        "success": cos_sim > 0.8,
        "defence_hint": "DP-SGD (clip=1.0, sigma=0.5) on the per-sample gradient destroys signal",
    }
