"""Shokri et al. 2017 shadow-model membership inference against a MAPPO policy.

Concept taught: a model's *confidence* on a sample is systematically
higher when the sample came from its training set than when it did
not. By training N small "shadow models" on disjoint sub-sets and
labelling their outputs as (in, out), an adversary fits a meta-
classifier that takes a confidence vector from the target model and
returns a membership label — even without any plaintext gradient.

We implement Shokri's idea against a softmax policy net (analogous to
the MAPPO actor): each shadow model is a tiny Linear classifier; the
attack model is a logistic regression on the shadow confidence vectors.

Defence
-------
DP-SGD during training (Gaussian noise on per-sample clipped
gradients) plus output-confidence clipping reduces the attack
advantage to <1% at ε = 1.0 — see `penumbra_learning.federated_dp`.
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


@dataclass(frozen=True, slots=True)
class ShadowDataset:
    members: NDArray[np.float64]  # (n, d)
    member_labels: NDArray[np.int_]
    non_members: NDArray[np.float64]
    non_member_labels: NDArray[np.int_]


def train_shadow_models(
    n: int = 5,
    *,
    n_features: int = 6,
    n_classes: int = 4,
    samples_per_shadow: int = 80,
    epochs: int = 60,
    seed: int = 42,
) -> tuple[list[nn.Linear], NDArray[np.float64], NDArray[np.int_]]:
    """Train n shadow classifiers; return them + (confidence_vec, in_label) records."""
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed=seed)

    shadow_nets: list[nn.Linear] = []
    confidences: list[NDArray[np.float64]] = []
    in_labels: list[int] = []

    for s in range(n):
        ds = _synthetic_dataset(
            n_features=n_features,
            n_classes=n_classes,
            n_per_set=samples_per_shadow,
            rng=np.random.default_rng(seed + s),
        )
        net = nn.Linear(n_features, n_classes)
        opt = torch.optim.Adam(net.parameters(), lr=0.05)
        x_train = torch.from_numpy(ds.members.astype(np.float32))
        y_train = torch.from_numpy(ds.member_labels.astype(np.int64))
        loss_fn = nn.CrossEntropyLoss()
        for _ in range(epochs):
            opt.zero_grad()
            logits = net(x_train)
            loss = loss_fn(logits, y_train)
            loss.backward()
            opt.step()
        shadow_nets.append(net)

        with torch.no_grad():
            for x, y in zip(ds.members, ds.member_labels, strict=True):
                probs = torch.softmax(net(torch.from_numpy(x.astype(np.float32))), dim=-1).numpy()
                confidences.append(_attack_features(probs, int(y)))
                in_labels.append(1)
            for x, y in zip(ds.non_members, ds.non_member_labels, strict=True):
                probs = torch.softmax(net(torch.from_numpy(x.astype(np.float32))), dim=-1).numpy()
                confidences.append(_attack_features(probs, int(y)))
                in_labels.append(0)
        _ = rng
    return shadow_nets, np.stack(confidences), np.asarray(in_labels)


def attack(
    target_observation: NDArray[np.float64],
    target_label: int,
    mappo_policy: nn.Module,
    attack_model: tuple[NDArray[np.float64], float],
) -> AttackResult:
    """Decide if `target_observation` was in the target model's training set."""
    weights, bias = attack_model
    with torch.no_grad():
        logits = mappo_policy(torch.from_numpy(target_observation.astype(np.float32)))
        probs = torch.softmax(logits, dim=-1).numpy()
    features = _attack_features(probs, int(target_label))
    score = float(features @ weights + bias)
    confidence = 1.0 / (1.0 + np.exp(-score))
    return AttackResult(
        success=bool(confidence > 0.5),
        evidence={
            "in_training": bool(confidence > 0.5),
            "confidence": float(confidence),
            "target_label": int(target_label),
            "max_softmax": float(probs.max()),
        },
    )


def fit_attack_model(
    features: NDArray[np.float64], in_labels: NDArray[np.int_]
) -> tuple[NDArray[np.float64], float]:
    """Fit a closed-form ridge logistic-regression on the shadow records."""
    design = np.hstack([features, np.ones((features.shape[0], 1))])
    y = in_labels.astype(np.float64) - 0.5
    reg = 1e-2 * np.eye(design.shape[1])
    sol = np.linalg.solve(design.T @ design + reg, design.T @ y)
    return sol[:-1].astype(np.float64), float(sol[-1])


def _attack_features(probs: NDArray[np.float64], label: int) -> NDArray[np.float64]:
    """Top-2 confidence + entropy + label confidence — the canonical Shokri features."""
    sorted_p = np.sort(probs)[::-1]
    top1 = float(sorted_p[0])
    top2 = float(sorted_p[1]) if sorted_p.size > 1 else 0.0
    eps = 1e-12
    entropy = float(-np.sum(probs * np.log(probs + eps)))
    label_conf = float(probs[label]) if 0 <= label < probs.shape[0] else 0.0
    return np.array([top1, top2, entropy, label_conf])


def _synthetic_dataset(
    *, n_features: int, n_classes: int, n_per_set: int, rng: np.random.Generator
) -> ShadowDataset:
    """Class-conditional Gaussians; disjoint train/non-member draws."""
    centres = rng.standard_normal((n_classes, n_features)) * 3.0

    def _draw(n: int) -> tuple[NDArray[np.float64], NDArray[np.int_]]:
        labels = rng.integers(0, n_classes, size=n)
        x = centres[labels] + rng.standard_normal((n, n_features))
        return x, labels

    members, member_labels = _draw(n_per_set)
    non_members, non_member_labels = _draw(n_per_set)
    return ShadowDataset(members, member_labels, non_members, non_member_labels)


def demo(*, n_shadows: int = 4, seed: int = 42) -> dict[str, object]:
    """End-to-end: train shadows, fit attack model, score against a target."""
    torch.manual_seed(seed)

    _, features, labels = train_shadow_models(
        n_shadows, n_features=4, n_classes=3, samples_per_shadow=40, epochs=40, seed=seed
    )
    attack_model = fit_attack_model(features, labels)

    target_rng = np.random.default_rng(seed + 999)
    target_ds = _synthetic_dataset(n_features=4, n_classes=3, n_per_set=50, rng=target_rng)
    target_net = nn.Linear(4, 3)
    opt = torch.optim.Adam(target_net.parameters(), lr=0.05)
    x_t = torch.from_numpy(target_ds.members.astype(np.float32))
    y_t = torch.from_numpy(target_ds.member_labels.astype(np.int64))
    loss_fn = nn.CrossEntropyLoss()
    for _ in range(60):
        opt.zero_grad()
        loss = loss_fn(target_net(x_t), y_t)
        loss.backward()
        opt.step()

    correct = 0
    total = 0
    for x, y in zip(target_ds.members, target_ds.member_labels, strict=True):
        r = attack(x, int(y), target_net, attack_model)
        correct += int(bool(r.evidence["in_training"]))
        total += 1
    for x, y in zip(target_ds.non_members, target_ds.non_member_labels, strict=True):
        r = attack(x, int(y), target_net, attack_model)
        correct += int(not bool(r.evidence["in_training"]))
        total += 1
    advantage = correct / total - 0.5
    return {
        "available": True,
        "algorithm": "Shokri et al. shadow-model MI (4 shadow nets + ridge logistic attack)",
        "n_shadows": n_shadows,
        "membership_accuracy": correct / total,
        "advantage_over_chance": float(advantage),
        "success": advantage > 0.05,
        "defence_hint": "DP-SGD (ε=1.0) + output-confidence clipping drops advantage below 1%",
    }
