"""Tests for k-anonymity (suppression mode)."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from penumbra_crypto.defenses.k_anonymity import (
    KAnonymityError,
    demo,
    evaluate_tradeoff,
    k_anonymise,
)


def _records(n: int = 100) -> list[dict[str, object]]:
    rng = np.random.default_rng(seed=42)
    return [
        {
            "city": str(rng.choice(["A", "B", "C"])),
            "product": str(rng.choice(["food", "tools"])),
            "agent_id": int(rng.integers(0, 25)),
        }
        for _ in range(n)
    ]


def test_empty_input_returns_empty() -> None:
    assert k_anonymise([], ["city"], k=3) == []


def test_k_one_is_identity() -> None:
    records = _records(20)
    out = k_anonymise(records, ["city", "product"], k=1)
    assert len(out) == len(records)


def test_k_too_large_suppresses_all() -> None:
    records = _records(10)
    out = k_anonymise(records, ["city", "product"], k=1000)
    assert out == []


def test_invalid_k_rejected() -> None:
    with pytest.raises(KAnonymityError):
        k_anonymise(_records(5), ["city"], k=0)


def test_empty_quasi_identifiers_rejected() -> None:
    with pytest.raises(KAnonymityError):
        k_anonymise(_records(5), [], k=2)


def test_each_surviving_bucket_has_at_least_k() -> None:
    """The output's quasi-id buckets all satisfy the k constraint."""
    from collections import Counter

    records = _records(150)
    k = 5
    out = k_anonymise(records, ["city", "product"], k=k)
    counts = Counter((r["city"], r["product"]) for r in out)
    assert all(c >= k for c in counts.values())


def test_suppression_rate_monotone_in_k() -> None:
    records = _records(200)
    last = 0.0
    for k in (1, 2, 3, 5, 8, 13, 21, 34):
        report = evaluate_tradeoff(records, ["city", "product"], k)
        assert report.suppression_rate >= last - 1e-9
        last = report.suppression_rate


def test_adversary_advantage_decreases_in_k() -> None:
    records = _records(200)
    last = 2.0
    for k in (1, 2, 3, 5, 8, 13):
        report = evaluate_tradeoff(records, ["city", "product"], k)
        assert report.adversary_max_reidentification <= last + 1e-9
        last = report.adversary_max_reidentification


def test_demo_returns_curve() -> None:
    payload = demo()
    assert payload["available"] is True
    curve = payload["curve"]
    assert isinstance(curve, list)
    assert len(curve) == 7
    ks = [int(p["k"]) for p in curve]
    assert ks == sorted(ks)


@settings(max_examples=20, deadline=None)
@given(st.integers(min_value=1, max_value=15))
def test_property_output_count_does_not_exceed_input(k: int) -> None:
    records = _records(80)
    out = k_anonymise(records, ["city", "product"], k=k)
    assert len(out) <= len(records)


def test_no_input_mutation() -> None:
    records = _records(40)
    snapshot = [dict(r) for r in records]
    _ = k_anonymise(records, ["city", "product"], k=5)
    assert records == snapshot
