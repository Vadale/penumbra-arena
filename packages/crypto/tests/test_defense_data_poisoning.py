"""Tests for the defensive data-poisoning module."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from penumbra_crypto.defenses.data_poisoning import (
    DECOY_FLAG,
    PoisoningError,
    demo,
    evaluate_tradeoff,
    inject_decoy_traces,
)


def _records(n: int = 50) -> list[dict[str, object]]:
    rng = np.random.default_rng(seed=123)
    return [
        {
            "agent_id": int(rng.integers(0, 50)),
            "wealth": float(rng.normal(loc=100.0, scale=20.0)),
            "city": str(rng.choice(["A", "B", "C"])),
        }
        for _ in range(n)
    ]


def test_empty_input_returns_empty() -> None:
    assert inject_decoy_traces([], rate=0.1) == []


def test_zero_rate_returns_only_real_with_flag() -> None:
    records = _records(20)
    out = inject_decoy_traces(records, rate=0.0, rng=np.random.default_rng(seed=1))
    assert len(out) == len(records)
    assert all(r[DECOY_FLAG] is False for r in out)


def test_rate_one_doubles_record_count() -> None:
    records = _records(20)
    out = inject_decoy_traces(records, rate=1.0, rng=np.random.default_rng(seed=1))
    assert len(out) == 40
    assert sum(1 for r in out if r[DECOY_FLAG]) == 20


def test_invalid_rate_raises() -> None:
    with pytest.raises(PoisoningError):
        inject_decoy_traces(_records(5), rate=-0.1)
    with pytest.raises(PoisoningError):
        inject_decoy_traces(_records(5), rate=1.5)


def test_existing_decoy_flag_rejected() -> None:
    bad = [{"agent_id": 1, DECOY_FLAG: True}]
    with pytest.raises(PoisoningError):
        inject_decoy_traces(bad, rate=0.1)


def test_decoys_share_schema_with_real() -> None:
    records = _records(30)
    out = inject_decoy_traces(records, rate=0.3, rng=np.random.default_rng(seed=2))
    real_fields = set(records[0].keys()) | {DECOY_FLAG}
    for r in out:
        assert set(r.keys()) == real_fields


def test_decoy_values_drawn_from_empirical_support() -> None:
    """A naive adversary checking value ranges can't filter decoys."""
    records = _records(30)
    cities = {r["city"] for r in records}
    out = inject_decoy_traces(records, rate=0.5, rng=np.random.default_rng(seed=3))
    decoy_cities = {r["city"] for r in out if r[DECOY_FLAG]}
    assert decoy_cities.issubset(cities)


def test_real_records_preserved_verbatim() -> None:
    """Every real input record must appear in the output (with the flag)."""
    records = _records(15)
    out = inject_decoy_traces(records, rate=0.4, rng=np.random.default_rng(seed=4))
    real_out = [{k: v for k, v in r.items() if k != DECOY_FLAG} for r in out if not r[DECOY_FLAG]]

    # Order may differ — sort canonically for comparison.
    def key(r: dict[str, object]) -> tuple[object, ...]:
        return tuple(sorted(r.items()))

    assert sorted(real_out, key=key) == sorted(records, key=key)


def test_evaluate_tradeoff_attacker_accuracy_monotone() -> None:
    """Adversary max accuracy must NOT increase with poisoning rate."""
    records = _records(100)
    last = 1.0
    for rate in (0.0, 0.1, 0.25, 0.5, 0.75, 1.0):
        report = evaluate_tradeoff(records, "wealth", rate=rate, rng=np.random.default_rng(seed=10))
        assert report.attacker_max_accuracy <= last + 1e-9
        last = report.attacker_max_accuracy


def test_demo_returns_curve_with_six_points() -> None:
    payload = demo()
    assert payload["available"] is True
    curve = payload["curve"]
    assert isinstance(curve, list)
    assert len(curve) == 6
    for point in curve:
        assert "rate" in point
        assert "attacker_max_accuracy" in point
        assert "utility_mean_shift" in point


@settings(max_examples=20, deadline=None)
@given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
def test_property_rate_within_bounds_produces_valid_output(rate: float) -> None:
    records = _records(20)
    out = inject_decoy_traces(records, rate=rate, rng=np.random.default_rng(seed=7))
    assert len(out) >= len(records)
    # The flag is always present.
    assert all(DECOY_FLAG in r for r in out)
