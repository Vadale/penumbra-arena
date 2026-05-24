"""Round-trip tests for CKKS context + DP budget persistence."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
from penumbra_crypto.ckks import TenSEALBackend
from penumbra_crypto.crypto_persistence import (
    load_dp_budget,
    restore_ckks_backend,
    save_ckks_context,
    save_dp_budget,
)
from penumbra_crypto.dp import PrivacyBudget


def test_ckks_save_restore_preserves_decryption_capability() -> None:
    """Cipher encrypted with backend A must decrypt under restored backend B."""
    a = TenSEALBackend()
    plain = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
    cipher = a.encrypt(plain)

    with tempfile.TemporaryDirectory() as tmpdir:
        ckks_path = Path(tmpdir) / "ckks_context.bin"
        save_ckks_context(a, ckks_path)
        restored = restore_ckks_backend(ckks_path)

    # The restored object IS a TenSEALBackend; cast through the same
    # type for static checkers.
    assert isinstance(restored, TenSEALBackend)
    cipher_b = restored.encrypt(plain)
    decrypted = restored.decrypt(cipher_b)[: len(plain)]
    assert np.allclose(decrypted, plain, atol=1e-3)
    # And the ciphertext encrypted with the ORIGINAL backend still
    # decrypts under the restored one — confirming the secret key
    # survived the round trip.
    assert np.allclose(restored.decrypt(cipher)[: len(plain)], plain, atol=1e-3)


def test_dp_budget_roundtrip_preserves_spent() -> None:
    budget = PrivacyBudget(epsilon=2.0, delta=1e-6)
    budget.deduct(0.7, 1e-7)
    budget.deduct(0.3, 1e-7)
    assert pytest.approx(budget.epsilon_spent) == 1.0
    assert pytest.approx(budget.delta_spent) == 2e-7

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "dp_budget.json"
        save_dp_budget(budget, path)
        restored = load_dp_budget(path)

    assert restored.epsilon == budget.epsilon
    assert restored.delta == budget.delta
    assert pytest.approx(restored.epsilon_spent) == 1.0
    assert pytest.approx(restored.delta_spent) == 2e-7

    # Restored accountant must continue refusing overdraws.
    from penumbra_crypto.dp import BudgetExceededError

    with pytest.raises(BudgetExceededError):
        restored.deduct(1.5)


def test_save_ckks_context_rejects_non_tenseal_backend() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "ckks_context.bin"
        with pytest.raises(TypeError):
            save_ckks_context(object(), path)


def test_load_dp_budget_missing_raises() -> None:
    with tempfile.TemporaryDirectory() as tmpdir, pytest.raises(FileNotFoundError):
        load_dp_budget(Path(tmpdir) / "missing.json")


def test_atomic_write_preserves_original_on_mid_write_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Crypto-audit closure: a crash between tmp-write and rename must
    leave the destination file untouched.

    We simulate the crash by monkeypatching ``os.replace`` (the last step
    of the atomic write) to raise. A successful first write seeds the
    file; the second write fails mid-flight; the file must still hold
    the FIRST payload, never a truncation."""
    import os

    from penumbra_crypto.crypto_persistence import _atomic_write_text

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "dp_budget.json"

        first = '{"epsilon": 1.0, "delta": 1e-5, "epsilon_spent": 0.0, "delta_spent": 0.0}'
        _atomic_write_text(path, first)
        assert path.read_text() == first

        real_replace = os.replace

        def crashing_replace(*_args: object, **_kwargs: object) -> None:
            raise OSError("simulated crash between write and rename")

        monkeypatch.setattr(os, "replace", crashing_replace)
        with pytest.raises(OSError, match="simulated crash"):
            _atomic_write_text(path, '{"corrupted": "payload"}')

        # The destination still holds the original payload — the .tmp
        # may exist, but `path` itself is untouched.
        monkeypatch.setattr(os, "replace", real_replace)
        assert path.read_text() == first
