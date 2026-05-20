"""Tests for ML-KEM-768 and ML-DSA-65."""

from __future__ import annotations

import os

import pytest
from penumbra_crypto.pq import (
    kem_decapsulate,
    kem_encapsulate,
    kem_keygen,
    sig_keygen,
    sign,
    verify,
)


def test_kem_roundtrip() -> None:
    """encapsulate(pk) → ct, ss; decapsulate(sk, ct) → ss."""
    keypair = kem_keygen()
    result = kem_encapsulate(keypair.public_key)
    recovered = kem_decapsulate(keypair.secret_key, result.ciphertext)
    assert recovered == result.shared_secret


def test_kem_shared_secret_is_32_bytes() -> None:
    keypair = kem_keygen()
    result = kem_encapsulate(keypair.public_key)
    assert len(result.shared_secret) == 32


def test_kem_decapsulate_with_wrong_secret_returns_garbage() -> None:
    """Implicit rejection: a wrong sk decapsulates to a deterministic but
    unpredictable byte string, NOT the original shared secret."""
    keypair_a = kem_keygen()
    keypair_b = kem_keygen()
    result = kem_encapsulate(keypair_a.public_key)
    garbage = kem_decapsulate(keypair_b.secret_key, result.ciphertext)
    assert garbage != result.shared_secret


def test_kem_distinct_encapsulations_yield_distinct_secrets() -> None:
    keypair = kem_keygen()
    a = kem_encapsulate(keypair.public_key)
    b = kem_encapsulate(keypair.public_key)
    assert a.shared_secret != b.shared_secret
    assert a.ciphertext != b.ciphertext


def test_sig_roundtrip() -> None:
    keypair = sig_keygen()
    message = b"penumbra: agent 42 moves north"
    signature = sign(keypair.secret_key, message)
    assert verify(keypair.public_key, message, signature)


def test_sig_rejects_modified_message() -> None:
    keypair = sig_keygen()
    message = b"penumbra: legal move"
    signature = sign(keypair.secret_key, message)
    tampered = b"penumbra: forged move"
    assert not verify(keypair.public_key, tampered, signature)


def test_sig_rejects_modified_signature() -> None:
    keypair = sig_keygen()
    message = b"penumbra: legal move"
    signature = sign(keypair.secret_key, message)
    if len(signature) > 0:
        tampered = bytearray(signature)
        tampered[0] ^= 0xFF
        assert not verify(keypair.public_key, message, bytes(tampered))


def test_sig_rejects_wrong_pubkey() -> None:
    keypair_a = sig_keygen()
    keypair_b = sig_keygen()
    message = b"penumbra"
    signature = sign(keypair_a.secret_key, message)
    assert not verify(keypair_b.public_key, message, signature)


def test_sig_rejects_garbage_signature() -> None:
    keypair = sig_keygen()
    assert not verify(keypair.public_key, b"msg", b"\x00" * 32)


def test_keys_have_expected_byte_lengths() -> None:
    """Sanity-check that the wheels we installed match the NIST sizes."""
    kem = kem_keygen()
    sig = sig_keygen()
    # ML-KEM-768: pk=1184, sk=2400, ct=1088, ss=32
    assert len(kem.public_key) == 1184
    assert len(kem.secret_key) == 2400
    # ML-DSA-65: pk=1952, sk=4032; signature size ≈ 3309 (NIST FIPS 204).
    assert len(sig.public_key) == 1952
    assert len(sig.secret_key) == 4032


@pytest.mark.skipif(os.environ.get("CI") == "true", reason="randomness test, skip in CI")
def test_distinct_keypairs_diverge() -> None:
    a = sig_keygen()
    b = sig_keygen()
    assert a.public_key != b.public_key
    assert a.secret_key != b.secret_key
