"""Tests for request obfuscation (Bonferroni + dummy queries)."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from penumbra_crypto.defenses.request_obfuscation import (
    DUMMY_FLAG,
    ObfuscationError,
    add_dummy_queries,
    bonferroni_correct_queries,
    demo,
    evaluate_tradeoff,
)


def _queries(n: int = 10) -> list[dict[str, object]]:
    rng = np.random.default_rng(seed=11)
    return [
        {
            "target_agent": int(rng.integers(0, 50)),
            "metric": str(rng.choice(["wealth", "position", "trades"])),
            "epsilon_request": float(rng.uniform(0.01, 0.2)),
        }
        for _ in range(n)
    ]


def test_bonferroni_empty_input_returns_empty() -> None:
    assert bonferroni_correct_queries([], family_size=5) == []


def test_bonferroni_per_query_eps_correct() -> None:
    queries = _queries(10)
    out = bonferroni_correct_queries(queries, family_wise_epsilon=1.0)
    for q in out:
        assert pytest.approx(q["epsilon_corrected"]) == 0.1
        assert q["family_size"] == 10


def test_bonferroni_uses_max_of_family_and_actual() -> None:
    """family_size acts as a lower bound; actual count wins if larger."""
    queries = _queries(20)
    out = bonferroni_correct_queries(queries, family_size=5, family_wise_epsilon=1.0)
    assert pytest.approx(out[0]["epsilon_corrected"]) == 1.0 / 20
    assert out[0]["family_size"] == 20


def test_bonferroni_invalid_epsilon_rejected() -> None:
    with pytest.raises(ObfuscationError):
        bonferroni_correct_queries(_queries(3), family_wise_epsilon=0.0)


def test_dummy_queries_count() -> None:
    queries = _queries(10)
    out = add_dummy_queries(queries, n_dummies=5, rng=np.random.default_rng(seed=1))
    assert len(out) == 15
    assert sum(1 for q in out if q[DUMMY_FLAG]) == 5
    assert sum(1 for q in out if not q[DUMMY_FLAG]) == 10


def test_dummy_queries_zero_returns_real_with_flag() -> None:
    queries = _queries(8)
    out = add_dummy_queries(queries, n_dummies=0, rng=np.random.default_rng(seed=1))
    assert len(out) == 8
    assert all(q[DUMMY_FLAG] is False for q in out)


def test_dummy_negative_count_rejected() -> None:
    with pytest.raises(ObfuscationError):
        add_dummy_queries(_queries(3), n_dummies=-1)


def test_dummy_flag_collision_rejected() -> None:
    bad = [{"target_agent": 1, DUMMY_FLAG: False}]
    with pytest.raises(ObfuscationError):
        add_dummy_queries(bad, n_dummies=1)


def test_dummy_schema_preserved() -> None:
    queries = _queries(10)
    out = add_dummy_queries(queries, n_dummies=5, rng=np.random.default_rng(seed=2))
    expected = set(queries[0].keys()) | {DUMMY_FLAG}
    for q in out:
        assert set(q.keys()) == expected


def test_evaluate_tradeoff_inflation_equals_family_size() -> None:
    queries = _queries(10)
    report = evaluate_tradeoff(
        queries, n_dummies=20, family_wise_epsilon=1.0, rng=np.random.default_rng(seed=1)
    )
    assert report.attacker_budget_inflation == float(report.family_size)
    assert report.family_size == 30  # 10 real + 20 dummies


def test_evaluate_tradeoff_per_query_eps_decreases_in_n_dummies() -> None:
    queries = _queries(10)
    last = 1.0
    for nd in (0, 5, 10, 20, 40):
        r = evaluate_tradeoff(
            queries,
            n_dummies=nd,
            family_wise_epsilon=1.0,
            rng=np.random.default_rng(seed=2),
        )
        assert r.per_query_epsilon_corrected <= last + 1e-9
        last = r.per_query_epsilon_corrected


def test_evaluate_tradeoff_empty_rejected() -> None:
    with pytest.raises(ObfuscationError):
        evaluate_tradeoff([], n_dummies=1)


def test_demo_returns_curve() -> None:
    payload = demo()
    assert payload["available"] is True
    curve = payload["curve"]
    assert isinstance(curve, list)
    assert len(curve) == 6
    assert all("attacker_budget_inflation" in p for p in curve)


def test_no_input_mutation() -> None:
    queries = _queries(8)
    snapshot = [dict(q) for q in queries]
    _ = bonferroni_correct_queries(queries, family_wise_epsilon=1.0)
    _ = add_dummy_queries(queries, n_dummies=4, rng=np.random.default_rng(seed=99))
    assert queries == snapshot


@settings(max_examples=20, deadline=None)
@given(st.integers(min_value=0, max_value=50))
def test_property_dummy_count_matches_request(n_dummies: int) -> None:
    queries = _queries(5)
    out = add_dummy_queries(queries, n_dummies=n_dummies, rng=np.random.default_rng(seed=4))
    assert sum(1 for q in out if q[DUMMY_FLAG]) == n_dummies
