"""Property tests for the agent-fingerprinting attack."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from penumbra_attacker.attacks import agent_fingerprint


def test_demo_reidentifies_above_chance() -> None:
    result = agent_fingerprint.demo(n_agents=6, n_window_matches=5, seed=7)
    assert result["available"] is True
    acc = float(result["reidentification_accuracy"])  # type: ignore[arg-type]
    baseline = float(result["random_baseline"])  # type: ignore[arg-type]
    assert acc > baseline


def test_attack_envelope_evidence_keys() -> None:
    result = agent_fingerprint.demo(n_agents=4, n_window_matches=4, seed=1)
    for key in ("reidentification_accuracy", "random_baseline", "n_agents", "defence_hint"):
        assert key in result


@settings(max_examples=8, deadline=None)
@given(st.integers(min_value=3, max_value=8), st.integers(min_value=2, max_value=5))
def test_demo_accuracy_in_unit_interval(n_agents: int, n_matches: int) -> None:
    result = agent_fingerprint.demo(n_agents=n_agents, n_window_matches=n_matches, seed=42)
    acc = result["reidentification_accuracy"]
    assert isinstance(acc, float)
    assert 0.0 <= acc <= 1.0


def test_attack_on_empty_db_returns_failure() -> None:
    result = agent_fingerprint.attack({}, {})
    assert result.success is False


def test_fingerprint_dimension_stable() -> None:
    rng = np.random.default_rng(0)
    traces = [
        agent_fingerprint.AgentTrace(
            agent_id=i,
            action_ids=rng.integers(0, 8, size=20),
            latencies_us=rng.normal(100, 5, size=20),
            positions=rng.standard_normal((20, 2)),
            trade_counts=rng.integers(0, 5, size=3),
        )
        for i in range(3)
    ]
    fp = agent_fingerprint.fingerprint(traces)
    sizes = {v.shape[0] for v in fp.values()}
    assert len(sizes) == 1


@pytest.mark.parametrize("seed", [1, 17, 99])
def test_seeded_reproducibility(seed: int) -> None:
    a = agent_fingerprint.demo(n_agents=5, n_window_matches=3, seed=seed)
    b = agent_fingerprint.demo(n_agents=5, n_window_matches=3, seed=seed)
    assert a["reidentification_accuracy"] == b["reidentification_accuracy"]
