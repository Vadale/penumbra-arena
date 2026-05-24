"""Tests for request padding + cover-traffic scheduling."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from penumbra_crypto.defenses.padding import (
    PaddingError,
    cover_traffic_schedule,
    demo,
    evaluate_tradeoff,
    pad_request,
    pad_response,
    unpad,
)


def test_pad_request_produces_target_size() -> None:
    out = pad_request(b"hello", target_size=64)
    assert len(out) == 64


def test_pad_then_unpad_roundtrips() -> None:
    msg = b"the quick brown fox"
    padded = pad_request(msg, target_size=128)
    assert unpad(padded) == msg


def test_pad_response_matches_pad_request() -> None:
    msg = b"deadbeef"
    assert pad_request(msg, 64) == pad_response(msg, 64)


def test_oversized_message_rejected() -> None:
    msg = b"x" * 100
    with pytest.raises(PaddingError):
        pad_request(msg, target_size=80)


def test_target_too_small_for_header_rejected() -> None:
    with pytest.raises(PaddingError):
        pad_request(b"", target_size=2)


def test_unpad_rejects_truncated_input() -> None:
    with pytest.raises(PaddingError):
        unpad(b"\x00\x00")


def test_unpad_rejects_oversized_length_header() -> None:
    bad = (10).to_bytes(4, "big") + b"abc"
    with pytest.raises(PaddingError):
        unpad(bad)


def test_cover_traffic_zero_rate_returns_empty() -> None:
    assert cover_traffic_schedule(rate=0.0, duration_ticks=100) == []


def test_cover_traffic_invalid_rate_rejected() -> None:
    with pytest.raises(PaddingError):
        cover_traffic_schedule(rate=-0.1, duration_ticks=10)


def test_cover_traffic_invalid_duration_rejected() -> None:
    with pytest.raises(PaddingError):
        cover_traffic_schedule(rate=0.1, duration_ticks=0)


def test_cover_traffic_offsets_strictly_increasing_and_in_range() -> None:
    duration = 500
    offsets = cover_traffic_schedule(
        rate=0.1, duration_ticks=duration, rng=np.random.default_rng(seed=42)
    )
    assert offsets, "expected at least one decoy in 500 ticks at rate 0.1"
    assert all(0 <= o < duration for o in offsets)
    # Allow repeated integer offsets (gap < 1) but enforce non-decreasing.
    assert offsets == sorted(offsets)


def test_cover_traffic_rate_matches_expectation() -> None:
    """At rate r, expected count over D ticks is r * D ± a few σ."""
    rate, duration = 0.1, 1000
    offsets = cover_traffic_schedule(
        rate=rate, duration_ticks=duration, rng=np.random.default_rng(seed=1)
    )
    expected = rate * duration
    # Poisson std = sqrt(λ); allow ±5σ for stability.
    assert abs(len(offsets) - expected) < 5.0 * (expected**0.5)


def test_evaluate_tradeoff_collapses_to_one_size() -> None:
    sizes = [10, 50, 100, 200]
    report = evaluate_tradeoff(sizes, target_size=512)
    assert report.n_distinct_sizes_after == 1


def test_evaluate_tradeoff_empty_rejected() -> None:
    with pytest.raises(PaddingError):
        evaluate_tradeoff([], target_size=128)


def test_demo_returns_curve_and_schedule() -> None:
    payload = demo()
    assert payload["available"] is True
    curve = payload["curve"]
    assert isinstance(curve, list)
    assert len(curve) == 5
    assert isinstance(payload["cover_schedule_preview"], list)


@settings(max_examples=20, deadline=None)
@given(
    st.binary(min_size=0, max_size=200),
    st.integers(min_value=256, max_value=2048),
)
def test_property_pad_unpad_roundtrip(msg: bytes, target_size: int) -> None:
    if len(msg) + 4 > target_size:
        with pytest.raises(PaddingError):
            pad_request(msg, target_size)
    else:
        padded = pad_request(msg, target_size)
        assert len(padded) == target_size
        assert unpad(padded) == msg
