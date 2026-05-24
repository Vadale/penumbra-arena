"""Tests for ℓ-diversity (suppression mode)."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from penumbra_crypto.defenses.l_diversity import (
    LDiversityError,
    demo,
    evaluate_tradeoff,
    l_diversify,
)


def _records(n: int = 200) -> list[dict[str, object]]:
    rng = np.random.default_rng(seed=42)
    return [
        {
            "city": str(rng.choice(["A", "B", "C"])),
            "product": str(rng.choice(["food", "tools"])),
            "diagnosis": str(rng.choice(["a", "b", "c", "d"])),
        }
        for _ in range(n)
    ]


def test_empty_input_returns_empty() -> None:
    assert l_diversify([], ["city"], "diagnosis", l=2) == []


def test_invalid_l_rejected() -> None:
    with pytest.raises(LDiversityError):
        l_diversify(_records(5), ["city"], "diagnosis", l=0)


def test_empty_quasi_id_rejected() -> None:
    with pytest.raises(LDiversityError):
        l_diversify(_records(5), [], "diagnosis", l=2)


def test_empty_sensitive_col_rejected() -> None:
    with pytest.raises(LDiversityError):
        l_diversify(_records(5), ["city"], "", l=2)


def test_each_surviving_bucket_has_at_least_l_distinct_sensitive() -> None:
    from collections import defaultdict

    records = _records(300)
    l = 3
    out = l_diversify(records, ["city", "product"], "diagnosis", l=l)
    sensitive_by_bucket: dict[tuple[object, ...], set[object]] = defaultdict(set)
    for r in out:
        key = (r["city"], r["product"])
        sensitive_by_bucket[key].add(r["diagnosis"])
    for vals in sensitive_by_bucket.values():
        assert len(vals) >= l


def test_l_one_with_k_three_matches_k_anonymity() -> None:
    """ℓ=1 reduces to plain k-anonymity (every bucket of size ≥ k passes)."""
    from penumbra_crypto.defenses.k_anonymity import k_anonymise

    records = _records(150)
    k = 3
    via_l = l_diversify(records, ["city", "product"], "diagnosis", l=1, k=k)
    via_k = k_anonymise(records, ["city", "product"], k=k)
    assert len(via_l) == len(via_k)


def test_suppression_rate_monotone_in_l() -> None:
    records = _records(400)
    last = 0.0
    for l in (1, 2, 3, 4):
        report = evaluate_tradeoff(records, ["city", "product"], "diagnosis", l, k=5)
        assert report.suppression_rate >= last - 1e-9
        last = report.suppression_rate


def test_homogeneity_safety_holds_when_released_non_empty() -> None:
    records = _records(400)
    report = evaluate_tradeoff(records, ["city", "product"], "diagnosis", l=2, k=5)
    if report.n_released > 0:
        assert report.homogeneity_safe is True


def test_demo_returns_curve() -> None:
    payload = demo()
    assert payload["available"] is True
    curve = payload["curve"]
    assert isinstance(curve, list)
    assert len(curve) == 4


@settings(max_examples=20, deadline=None)
@given(st.integers(min_value=1, max_value=4))
def test_property_output_count_does_not_exceed_input(l: int) -> None:
    records = _records(80)
    out = l_diversify(records, ["city", "product"], "diagnosis", l=l)
    assert len(out) <= len(records)


def test_no_input_mutation() -> None:
    records = _records(40)
    snapshot = [dict(r) for r in records]
    _ = l_diversify(records, ["city", "product"], "diagnosis", l=2)
    assert records == snapshot
