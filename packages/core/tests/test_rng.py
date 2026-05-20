"""Property tests for the central RNG.

The contract under test: identical seed → identical draws across stdlib
random, numpy, and (when present) torch. Distinct domains → uncorrelated
streams.
"""

from __future__ import annotations

import random

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from penumbra_core.rng import InvalidSeedError, Seeded, bootstrap, run_record


def _draw_sequence(seeded: Seeded, n: int = 64) -> tuple[list[float], np.ndarray]:
    """Pull a deterministic sample from stdlib random and the bootstrap numpy gen."""
    py = [random.random() for _ in range(n)]  # noqa: S311 — deterministic, not crypto
    nps = seeded.numpy.standard_normal(n)
    return py, nps


@given(st.integers(min_value=0, max_value=2**63 - 1))
def test_reproducibility_property(seed: int) -> None:
    """Same seed → bit-identical draws on both stdlib and numpy streams."""
    a = bootstrap(seed)
    py_a, np_a = _draw_sequence(a)

    b = bootstrap(seed)
    py_b, np_b = _draw_sequence(b)

    assert py_a == py_b
    np.testing.assert_array_equal(np_a, np_b)


def test_default_seed_when_env_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PENUMBRA_SEED", raising=False)
    seeded = bootstrap()
    assert seeded.master == 20260520


def test_env_var_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PENUMBRA_SEED", "7")
    seeded = bootstrap()
    assert seeded.master == 7


def test_invalid_env_var_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PENUMBRA_SEED", "not-an-int")
    with pytest.raises(InvalidSeedError):
        bootstrap()


def test_distinct_domains_diverge() -> None:
    """Two domains derived from the same master must produce different streams."""
    seeded = bootstrap(42)
    a = seeded.numpy_for("arena").standard_normal(32)
    b = seeded.numpy_for("agents").standard_normal(32)
    assert not np.allclose(a, b)


def test_same_domain_is_deterministic() -> None:
    """The same `(master, domain)` pair always yields the same stream."""
    a = bootstrap(42).numpy_for("arena").standard_normal(32)
    b = bootstrap(42).numpy_for("arena").standard_normal(32)
    np.testing.assert_array_equal(a, b)


def test_subkey_is_64_bit() -> None:
    seeded = bootstrap(42)
    sub = seeded.stream("arbitrary-domain-name")
    assert 0 <= sub < 2**64


def test_run_record_has_required_fields() -> None:
    seeded = bootstrap(42)
    record = run_record(seeded)
    assert record["master_seed"] == 42
    assert "started_at" in record
    assert "python" in record
    assert "numpy" in record


def test_seed_out_of_range_raises() -> None:
    with pytest.raises(InvalidSeedError):
        bootstrap(-1)
    with pytest.raises(InvalidSeedError):
        bootstrap(2**64)
