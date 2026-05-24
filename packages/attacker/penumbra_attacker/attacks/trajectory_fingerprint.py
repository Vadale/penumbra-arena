"""HMM trajectory fingerprinting: per-agent action-sequence classifier.

Concept taught: a hidden Markov model fitted on each agent's historical
action sequence captures *temporal* structure that a position-only
fingerprint misses. The transition + emission distributions become a
likelihood machine — classify an unknown trajectory by picking the
agent under whose HMM the sequence is most probable.

Defence
-------
DP-style action-level randomised response (RAPPOR-flavoured) before
release breaks the emission stability that the HMM depends on. Coupled
with per-match identity shuffling the best classifier collapses to 1/N.
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
class AgentHMM:
    """Tiny HMM: K hidden states, M action symbols."""

    agent_id: int
    transition: NDArray[np.float64]  # (K, K)
    emission: NDArray[np.float64]  # (K, M)
    initial: NDArray[np.float64]  # (K,)


def train_hmm(
    historical_traces: dict[int, list[NDArray[np.int_]]],
    *,
    n_states: int = 3,
    n_symbols: int = 8,
    n_iter: int = 8,
    seed: int = 42,
) -> dict[int, AgentHMM]:
    """Fit one HMM per agent via Baum-Welch (`n_iter` E-M passes)."""
    rng = np.random.default_rng(seed=seed)
    models: dict[int, AgentHMM] = {}
    for aid, traces in historical_traces.items():
        # Initialise with mild noise on uniforms (avoid degenerate symmetry).
        trans = _row_stochastic(
            np.ones((n_states, n_states)) + 0.1 * rng.random((n_states, n_states))
        )
        emit = _row_stochastic(
            np.ones((n_states, n_symbols)) + 0.1 * rng.random((n_states, n_symbols))
        )
        init = _row_stochastic(np.ones(n_states) + 0.1 * rng.random(n_states))[None, :][0]

        for _ in range(n_iter):
            trans, emit, init = _baum_welch_step(traces, trans, emit, init)
        models[aid] = AgentHMM(aid, trans, emit, init)
    return models


def attack_classify(unknown_trace: NDArray[np.int_], models: dict[int, AgentHMM]) -> AttackResult:
    """Pick the agent whose HMM assigns the highest log-likelihood to the trace."""
    if not models:
        return AttackResult(success=False, evidence={"reason": "no models"})
    best_aid = -1
    best_ll = -np.inf
    log_likelihoods: dict[int, float] = {}
    for aid, hmm in models.items():
        ll = _forward_log_likelihood(unknown_trace, hmm)
        log_likelihoods[aid] = float(ll)
        if ll > best_ll:
            best_ll = ll
            best_aid = aid
    return AttackResult(
        success=best_aid != -1,
        evidence={
            "predicted_agent": int(best_aid),
            "log_likelihood": float(best_ll),
            "per_agent_log_likelihood": log_likelihoods,
        },
    )


def _row_stochastic(matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.ndim == 1:
        return matrix / max(float(matrix.sum()), 1e-12)
    return matrix / np.clip(matrix.sum(axis=-1, keepdims=True), 1e-12, None)


def _forward_log_likelihood(obs: NDArray[np.int_], hmm: AgentHMM) -> float:
    """Scaled forward algorithm — returns Σ log scaling factors."""
    if obs.size == 0:
        return 0.0
    k = hmm.transition.shape[0]
    alpha = hmm.initial * hmm.emission[:, obs[0]]
    scale = float(alpha.sum())
    if scale <= 0.0:
        return -np.inf
    alpha /= scale
    log_lik = np.log(scale)
    for t in range(1, obs.shape[0]):
        alpha = (alpha @ hmm.transition) * hmm.emission[:, obs[t]]
        scale = float(alpha.sum())
        if scale <= 0.0:
            return -np.inf
        alpha /= scale
        log_lik += np.log(scale)
    _ = k
    return float(log_lik)


def _baum_welch_step(
    sequences: list[NDArray[np.int_]],
    transition: NDArray[np.float64],
    emission: NDArray[np.float64],
    initial: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """One E-M pass aggregated over all sequences for this agent."""
    k, m = emission.shape
    new_trans = np.full_like(transition, 1e-6)
    new_emit = np.full_like(emission, 1e-6)
    new_init = np.full_like(initial, 1e-6)

    for obs in sequences:
        t_len = obs.shape[0]
        if t_len == 0:
            continue
        alpha = np.zeros((t_len, k))
        scales = np.zeros(t_len)

        alpha[0] = initial * emission[:, obs[0]]
        scales[0] = max(alpha[0].sum(), 1e-12)
        alpha[0] /= scales[0]
        for t in range(1, t_len):
            alpha[t] = (alpha[t - 1] @ transition) * emission[:, obs[t]]
            scales[t] = max(alpha[t].sum(), 1e-12)
            alpha[t] /= scales[t]

        beta = np.zeros((t_len, k))
        beta[-1] = 1.0 / scales[-1]
        for t in range(t_len - 2, -1, -1):
            beta[t] = transition @ (emission[:, obs[t + 1]] * beta[t + 1])
            beta[t] /= scales[t]

        gamma = alpha * beta
        gamma_sum = gamma.sum(axis=1, keepdims=True)
        gamma = gamma / np.clip(gamma_sum, 1e-12, None)

        new_init += gamma[0]
        for t in range(t_len - 1):
            xi = (
                alpha[t][:, None]
                * transition
                * emission[None, :, obs[t + 1]]
                * beta[t + 1][None, :]
            )
            xi /= max(xi.sum(), 1e-12)
            new_trans += xi
        for t in range(t_len):
            new_emit[:, obs[t]] += gamma[t]
        _ = m

    return _row_stochastic(new_trans), _row_stochastic(new_emit), _row_stochastic(new_init)


def demo(*, n_agents: int = 5, n_train_matches: int = 4, seed: int = 42) -> dict[str, object]:
    """Train HMMs from synthetic action sequences and re-identify."""
    rng = np.random.default_rng(seed=seed)
    n_symbols = 6

    profiles = rng.dirichlet(np.ones(n_symbols), size=n_agents)

    def _sequence_for(aid: int, length: int = 40) -> NDArray[np.int_]:
        return rng.choice(n_symbols, size=length, p=profiles[aid])

    historical = {a: [_sequence_for(a) for _ in range(n_train_matches)] for a in range(n_agents)}
    models = train_hmm(historical, n_states=2, n_symbols=n_symbols, n_iter=6, seed=seed)

    correct = 0
    for a in range(n_agents):
        unknown = _sequence_for(a)
        result = attack_classify(unknown, models)
        if result.evidence.get("predicted_agent") == a:
            correct += 1
    accuracy = correct / n_agents
    return {
        "available": True,
        "algorithm": "Baum-Welch HMM (2 states) + forward log-likelihood scoring",
        "n_agents": n_agents,
        "n_train_matches": n_train_matches,
        "classification_accuracy": float(accuracy),
        "random_baseline": 1.0 / n_agents,
        "success": accuracy > 2.0 / n_agents,
        "defence_hint": "RAPPOR on action emissions + per-match shuffle collapses accuracy to 1/N",
    }
