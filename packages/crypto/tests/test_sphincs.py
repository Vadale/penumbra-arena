"""Tests for SPHINCS+ hash-based PQ signatures."""

from __future__ import annotations

from penumbra_crypto import sphincs


def test_sphincs_roundtrip() -> None:
    kp = sphincs.keygen()
    msg = b"penumbra-sphincs-roundtrip"
    sig = sphincs.sign(kp.secret_key, msg)
    assert sphincs.verify(kp.public_key, msg, sig)


def test_sphincs_rejects_wrong_message() -> None:
    kp = sphincs.keygen()
    sig = sphincs.sign(kp.secret_key, b"x")
    assert not sphincs.verify(kp.public_key, b"y", sig)


def test_sphincs_rejects_wrong_pubkey() -> None:
    a = sphincs.keygen()
    b = sphincs.keygen()
    sig = sphincs.sign(a.secret_key, b"shared")
    assert not sphincs.verify(b.public_key, b"shared", sig)


def test_sphincs_rejects_tampered_signature() -> None:
    kp = sphincs.keygen()
    sig = bytearray(sphincs.sign(kp.secret_key, b"m"))
    sig[0] ^= 0xFF
    assert not sphincs.verify(kp.public_key, b"m", bytes(sig))


def test_sphincs_signature_size_constant() -> None:
    kp = sphincs.keygen()
    for msg_len in (0, 1, 16, 1024):
        sig = sphincs.sign(kp.secret_key, b"x" * msg_len)
        assert len(sig) == sphincs.SIGNATURE_BYTES


def test_sphincs_demo() -> None:
    d = sphincs.demo()
    assert d["available"] is True
    assert d["honest_verifies"] is True
    assert d["tampered_message_verifies"] is False
    assert d["tampered_signature_verifies"] is False
    assert int(d["signature_bytes"]) > int(d["dilithium3_signature_bytes"])  # type: ignore[arg-type]
