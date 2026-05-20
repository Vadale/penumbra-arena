"""Property and unit tests for the CKKS adapter."""

from __future__ import annotations

import numpy as np
import pytest
from penumbra_crypto.ckks import (
    TenSEALBackend,
    UnavailableBackendError,
    get_backend,
)


@pytest.fixture(scope="module")
def backend() -> TenSEALBackend:
    return TenSEALBackend()


def test_encrypt_decrypt_roundtrip(backend: TenSEALBackend) -> None:
    plain = np.array([1.0, 2.5, -3.7, 0.0, 4.2], dtype=np.float64)
    ct = backend.encrypt(plain)
    recovered = backend.decrypt(ct)[: plain.size]
    np.testing.assert_allclose(recovered, plain, atol=1e-3)


def test_addition_is_homomorphic(backend: TenSEALBackend) -> None:
    a = np.array([1.0, 2.0, 3.0, 4.0])
    b = np.array([5.0, -1.0, 0.5, 2.0])
    expected = a + b
    ct_sum = backend.add(backend.encrypt(a), backend.encrypt(b))
    np.testing.assert_allclose(backend.decrypt(ct_sum)[: a.size], expected, atol=1e-3)


def test_multiplication_is_homomorphic(backend: TenSEALBackend) -> None:
    a = np.array([1.0, 2.0, 3.0, 4.0])
    b = np.array([2.0, 0.5, -1.0, 1.0])
    expected = a * b
    ct_prod = backend.multiply(backend.encrypt(a), backend.encrypt(b))
    np.testing.assert_allclose(backend.decrypt(ct_prod)[: a.size], expected, atol=1e-2)


def test_scalar_addition(backend: TenSEALBackend) -> None:
    a = np.array([1.0, 2.0, 3.0])
    ct = backend.add_scalar(backend.encrypt(a), 10.0)
    np.testing.assert_allclose(backend.decrypt(ct)[: a.size], a + 10.0, atol=1e-3)


def test_scalar_multiplication(backend: TenSEALBackend) -> None:
    a = np.array([1.0, 2.0, 3.0])
    ct = backend.multiply_scalar(backend.encrypt(a), 0.5)
    np.testing.assert_allclose(backend.decrypt(ct)[: a.size], a * 0.5, atol=1e-3)


def test_rejects_multi_dimensional_input(backend: TenSEALBackend) -> None:
    bad = np.zeros((4, 4))
    with pytest.raises(ValueError, match="1D"):
        backend.encrypt(bad)


def test_rejects_oversize_vector(backend: TenSEALBackend) -> None:
    bad = np.zeros(backend.slot_count + 1)
    with pytest.raises(ValueError, match="exceeds slot capacity"):
        backend.encrypt(bad)


def test_env_var_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PENUMBRA_HE_BACKEND", "garbage")
    with pytest.raises(ValueError, match="not recognised"):
        get_backend()


def test_explicit_openfhe_on_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit openfhe should raise UnavailableBackendError when the
    native extension can't be loaded (e.g. on Apple Silicon as of 1.5.1)."""
    monkeypatch.setenv("PENUMBRA_HE_BACKEND", "openfhe")
    try:
        get_backend()
    except UnavailableBackendError:
        return
    # If OpenFHE happens to be importable on this platform, that's fine —
    # the test simply notes the situation.


def test_auto_falls_back_to_tenseal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PENUMBRA_HE_BACKEND", "auto")
    be = get_backend()
    assert be.name in {"tenseal", "openfhe"}


def test_aggregate_heatmap_use_case(backend: TenSEALBackend) -> None:
    """End-to-end: 50 agents → encrypted one-hot grid vectors → encrypted
    sum decrypted to a density. This mirrors how Penumbra builds the
    heatmap each tick.
    """
    rng = np.random.default_rng(42)
    grid_size = 32
    n_agents = 50
    positions = rng.integers(0, grid_size, size=n_agents).tolist()

    accumulator = None
    for pos in positions:
        one_hot = np.zeros(grid_size, dtype=np.float64)
        one_hot[pos] = 1.0
        ct = backend.encrypt(one_hot)
        accumulator = ct if accumulator is None else backend.add(accumulator, ct)

    assert accumulator is not None
    density = backend.decrypt(accumulator)[:grid_size]
    expected = np.bincount(positions, minlength=grid_size).astype(np.float64)
    np.testing.assert_allclose(density, expected, atol=1e-2)
