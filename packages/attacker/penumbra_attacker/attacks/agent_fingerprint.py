"""Agent fingerprinting from observable behaviour.

Concept taught: even when agent identifiers are randomised, the
*statistics* of an agent's behaviour leak its identity. Per-action
inter-tick latency, action histogram, trajectory curvature and trade
pattern form a feature vector stable across matches — a 1-NN classifier
re-identifies agents with high accuracy.

Defence
-------
Randomised response on the action histogram + Laplace noise on
timings + per-match identity shuffling collapses the matcher's
accuracy to 1/N. The matched aggregate-noise level lives in
`penumbra_crypto.dp`.
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


@dataclass(frozen=True, slots=True)
class AgentTrace:
    """One agent's observable behaviour across a window of ticks."""

    agent_id: int
    action_ids: NDArray[np.int_]
    latencies_us: NDArray[np.float64]
    positions: NDArray[np.float64]  # (T, 2) trajectory
    trade_counts: NDArray[np.int_]  # (n_goods,)


def fingerprint(traces: list[AgentTrace], *, n_actions: int = 8) -> dict[int, NDArray[np.float64]]:
    """Project each trace to a feature vector that is stable across matches."""
    features: dict[int, NDArray[np.float64]] = {}
    for t in traces:
        action_hist = np.bincount(t.action_ids, minlength=n_actions).astype(np.float64)
        if action_hist.sum() > 0:
            action_hist /= action_hist.sum()
        latency_summary = np.array(
            [
                float(np.mean(t.latencies_us)) if t.latencies_us.size else 0.0,
                float(np.std(t.latencies_us)) if t.latencies_us.size else 0.0,
                float(np.median(t.latencies_us)) if t.latencies_us.size else 0.0,
            ]
        )
        curvature = _trajectory_curvature(t.positions)
        trade_norm = t.trade_counts.astype(np.float64)
        if trade_norm.sum() > 0:
            trade_norm = trade_norm / trade_norm.sum()
        features[t.agent_id] = np.concatenate([action_hist, latency_summary, curvature, trade_norm])
    return features


def attack(
    features: dict[int, NDArray[np.float64]],
    known_agents: dict[int, NDArray[np.float64]],
) -> AttackResult:
    """1-NN re-identification of unseen agents against a known fingerprint DB."""
    if not features or not known_agents:
        return AttackResult(success=False, evidence={"reason": "empty input"})

    known_ids = list(known_agents.keys())
    db = np.stack([known_agents[k] for k in known_ids])

    correct = 0
    total = 0
    for true_id, query in features.items():
        if true_id not in known_agents:
            continue
        distances = np.linalg.norm(db - query, axis=1)
        predicted = known_ids[int(np.argmin(distances))]
        correct += int(predicted == true_id)
        total += 1

    accuracy = correct / max(total, 1)
    n_classes = len(known_ids)
    random_baseline = 1.0 / max(n_classes, 1)
    return AttackResult(
        success=accuracy > 2.0 * random_baseline,
        evidence={
            "reidentification_accuracy": float(accuracy),
            "random_baseline": float(random_baseline),
            "n_classes": n_classes,
            "n_queries": total,
        },
    )


def _trajectory_curvature(positions: NDArray[np.float64]) -> NDArray[np.float64]:
    """Three-element summary of a 2D trajectory: total length, displacement, turning."""
    if positions.shape[0] < 3:
        return np.zeros(3)
    deltas = np.diff(positions, axis=0)
    path_length = float(np.sum(np.linalg.norm(deltas, axis=1)))
    displacement = float(np.linalg.norm(positions[-1] - positions[0]))
    cos_angles = np.einsum("ij,ij->i", deltas[:-1], deltas[1:])
    norms = np.linalg.norm(deltas[:-1], axis=1) * np.linalg.norm(deltas[1:], axis=1)
    cos_norm = cos_angles / np.clip(norms, 1e-9, None)
    turning = float(np.mean(1.0 - cos_norm))
    return np.array([path_length, displacement, turning])


def demo(*, n_agents: int = 8, n_window_matches: int = 6, seed: int = 42) -> dict[str, object]:
    """Simulate stable per-agent behaviour, fingerprint, then re-identify."""
    rng = np.random.default_rng(seed=seed)

    # Each agent has a stable behavioural profile across matches.
    action_prefs = rng.dirichlet(np.ones(8), size=n_agents)
    latency_means = rng.uniform(50.0, 200.0, size=n_agents)
    trade_prefs = rng.dirichlet(np.ones(3), size=n_agents)
    drifts = rng.standard_normal((n_agents, 2)) * 0.4

    def _trace_for(aid: int) -> AgentTrace:
        n_steps = 64
        actions = rng.choice(8, size=n_steps, p=action_prefs[aid])
        latencies = rng.normal(latency_means[aid], 5.0, size=n_steps)
        steps = rng.standard_normal((n_steps, 2)) * 0.1 + drifts[aid]
        positions = np.cumsum(steps, axis=0)
        trades = rng.multinomial(20, trade_prefs[aid])
        return AgentTrace(aid, actions, latencies, positions, trades)

    # Known DB: average features over historical matches.
    known: dict[int, list[NDArray[np.float64]]] = {a: [] for a in range(n_agents)}
    for _ in range(n_window_matches):
        traces = [_trace_for(a) for a in range(n_agents)]
        fp = fingerprint(traces)
        for a, v in fp.items():
            known[a].append(v)
    known_avg = {a: np.mean(np.stack(vs), axis=0) for a, vs in known.items()}

    # Unseen match: re-identify.
    test_traces = [_trace_for(a) for a in range(n_agents)]
    test_fp = fingerprint(test_traces)
    result = attack(test_fp, known_avg)

    return {
        "available": True,
        "algorithm": "1-NN over (action hist, latency stats, curvature, trades)",
        "n_agents": n_agents,
        "n_window_matches": n_window_matches,
        "reidentification_accuracy": result.evidence["reidentification_accuracy"],
        "random_baseline": result.evidence["random_baseline"],
        "success": result.success,
        "defence_hint": (
            "Randomised response on action histogram + Laplace on latency + "
            "per-match identity shuffle collapses accuracy to 1/N"
        ),
    }
