"""Property tests for the HMM trajectory-fingerprinting attack."""

from __future__ import annotations

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from penumbra_attacker.attacks import trajectory_fingerprint as tf


def test_demo_classifies_above_chance() -> None:
    result = tf.demo(n_agents=4, n_train_matches=4, seed=5)
    assert result["available"] is True
    acc = float(result["classification_accuracy"])  # type: ignore[arg-type]
    baseline = float(result["random_baseline"])  # type: ignore[arg-type]
    assert acc >= baseline


def test_train_hmm_returns_one_model_per_agent() -> None:
    rng = np.random.default_rng(0)
    traces = {a: [rng.integers(0, 4, size=20) for _ in range(3)] for a in range(3)}
    models = tf.train_hmm(traces, n_states=2, n_symbols=4, n_iter=2)
    assert set(models.keys()) == {0, 1, 2}


def test_classify_returns_known_agent_id() -> None:
    rng = np.random.default_rng(0)
    traces = {a: [rng.integers(0, 4, size=15)] for a in range(2)}
    models = tf.train_hmm(traces, n_states=2, n_symbols=4, n_iter=2)
    out = tf.attack_classify(np.array([0, 1, 2, 3, 0]), models)
    assert out.evidence["predicted_agent"] in {0, 1}


def test_classify_on_empty_models() -> None:
    out = tf.attack_classify(np.array([0, 1]), {})
    assert out.success is False


@settings(max_examples=4, deadline=None)
@given(st.integers(min_value=3, max_value=6))
def test_demo_accuracy_bounded(n_agents: int) -> None:
    result = tf.demo(n_agents=n_agents, n_train_matches=3, seed=42)
    acc = float(result["classification_accuracy"])  # type: ignore[arg-type]
    assert 0.0 <= acc <= 1.0
