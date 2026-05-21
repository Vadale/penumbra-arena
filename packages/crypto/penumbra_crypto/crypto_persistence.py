"""Disk persistence for CKKS context + DP budget.

Concept taught: keys outlive processes. Without persistence, every
restart of the Penumbra backend re-generates a fresh CKKS keypair —
meaning any ciphertext saved to disk before the restart is forever
undecipherable, and the DP accountant resets to "fresh budget" so
a malicious operator could overdraw by simply bouncing the process.

This module gives both pieces a durable on-disk form:
- CKKS context as TenSEAL's native binary serialization (includes
  secret + relin + galois keys).
- PrivacyBudget as JSON {epsilon, delta, epsilon_spent, delta_spent}.

Both live under `state/snapshots/<name>/crypto/`:
  ckks_context.bin
  dp_budget.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from penumbra_crypto.dp import PrivacyBudget


def save_ckks_context(backend: object, path: Path) -> None:
    """Serialize a TenSEAL CKKS context to disk.

    Includes the secret key so the same backend can decrypt later;
    file is chmod 0o600 for owner-only read.
    """
    serializer = getattr(backend, "_context", None)
    if serializer is None or not hasattr(serializer, "serialize"):
        raise TypeError("save_ckks_context expects a TenSEALBackend; got " + type(backend).__name__)
    raw: bytes = serializer.serialize(
        save_public_key=True,
        save_secret_key=True,
        save_galois_keys=True,
        save_relin_keys=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    # Crypto-audit B1: atomic 0o600 write closes the TOCTOU between
    # path.write_bytes (creates the file with default umask, often 0o644)
    # and the subsequent chmod call.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(str(path), flags, 0o600)
    try:
        os.write(fd, raw)
    finally:
        os.close(fd)


def load_ckks_context_bytes(path: Path) -> bytes:
    """Read the serialized CKKS bytes from disk (raises if missing)."""
    if not path.is_file():
        raise FileNotFoundError(f"CKKS context not found at {path}")
    return path.read_bytes()


def restore_ckks_backend(path: Path) -> object:
    """Build a TenSEALBackend from a saved context file.

    Returns a TenSEALBackend whose `_context` is the restored TenSEAL
    Context; the rest of the backend (encrypt/decrypt/add/...)
    operates against it identically to a freshly-generated backend.
    """
    import tenseal as ts  # pyright: ignore[reportMissingImports]

    from penumbra_crypto.ckks import CKKSParameters, TenSEALBackend

    blob = load_ckks_context_bytes(path)
    context = ts.context_from(blob)

    # Build a fresh backend shell and swap in the loaded context.
    backend = TenSEALBackend.__new__(TenSEALBackend)
    backend.params = CKKSParameters()
    backend._ts = ts  # type: ignore[attr-defined]
    backend._context = context  # type: ignore[attr-defined]
    return backend


def save_dp_budget(budget: PrivacyBudget, path: Path) -> None:
    """Write the privacy-budget accountant to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "epsilon": budget.epsilon,
        "delta": budget.delta,
        "epsilon_spent": budget.epsilon_spent,
        "delta_spent": budget.delta_spent,
    }
    path.write_text(json.dumps(payload, indent=2))


def load_dp_budget(path: Path) -> PrivacyBudget:
    """Reverse `save_dp_budget`.

    Crypto-audit B3: refuse silent partial payloads. Earlier the loader
    fell back to `.get(..., 0.0)` for missing keys — a malicious operator
    could truncate the file to `{}` and reset `epsilon_spent` to zero,
    exactly the failure mode the accountant claims to prevent.
    """
    if not path.is_file():
        raise FileNotFoundError(f"DP budget snapshot not found at {path}")
    payload = json.loads(path.read_text())
    required = {"epsilon", "delta", "epsilon_spent", "delta_spent"}
    missing = required - set(payload.keys())
    if missing:
        raise ValueError(f"DP budget snapshot at {path} is missing keys: {sorted(missing)}")
    return PrivacyBudget(
        epsilon=float(payload["epsilon"]),
        delta=float(payload["delta"]),
        epsilon_spent=float(payload["epsilon_spent"]),
        delta_spent=float(payload["delta_spent"]),
    )
