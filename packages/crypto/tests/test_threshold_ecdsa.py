"""Tests for GG18-style threshold ECDSA."""

from __future__ import annotations

import pytest
from penumbra_crypto import threshold_ecdsa as tecdsa


def test_threshold_ecdsa_full_quorum_signs_and_verifies() -> None:
    shares = tecdsa.keygen(n=3)
    msg = b"penumbra-tecdsa-roundtrip"
    sig = tecdsa.sign(shares, msg)
    assert tecdsa.verify(shares[0].joint_public_key_x, shares[0].joint_public_key_y, msg, sig)


def test_threshold_ecdsa_rejects_tampered_message() -> None:
    shares = tecdsa.keygen(n=4)
    msg = b"penumbra-tecdsa-rejects"
    sig = tecdsa.sign(shares, msg)
    assert not tecdsa.verify(
        shares[0].joint_public_key_x,
        shares[0].joint_public_key_y,
        msg + b"!",
        sig,
    )


def test_threshold_ecdsa_rejects_tampered_signature() -> None:
    shares = tecdsa.keygen(n=2)
    msg = b"penumbra-tecdsa-tamper"
    sig = tecdsa.sign(shares, msg)
    forged = tecdsa.TECDSASignature(r=sig.r, s=(sig.s + 1) % (1 << 200))
    assert not tecdsa.verify(
        shares[0].joint_public_key_x, shares[0].joint_public_key_y, msg, forged
    )


def test_threshold_ecdsa_demands_full_quorum() -> None:
    shares = tecdsa.keygen(n=3)
    with pytest.raises(tecdsa.ThresholdECDSAError):
        tecdsa.sign(shares[:2], b"x")


def test_threshold_ecdsa_demo() -> None:
    d = tecdsa.demo(n=3)
    assert d["available"] is True
    assert d["honest_verifies"] is True
    assert d["tampered_message_verifies"] is False
    assert d["tampered_signature_verifies"] is False
