"""Tests for FROST threshold Schnorr signatures."""

from __future__ import annotations

import pytest
from penumbra_crypto import frost


def test_frost_keygen_consistent_public_key() -> None:
    shares = frost.keygen(n=5, t=3)
    assert len({s.group_public_key for s in shares}) == 1
    assert all(s.secret_share > 0 for s in shares)


def test_frost_threshold_signature_verifies() -> None:
    shares = frost.keygen(n=5, t=3)
    active = shares[:3]
    nonces = [frost.commit_nonces(s.index) for s in active]
    commits = [c for c, _ in nonces]
    witnesses = [w for _, w in nonces]
    msg = b"penumbra-frost-test"
    sig_shares = [
        frost.sign_share(s, w, msg, commits) for s, w in zip(active, witnesses, strict=True)
    ]
    sig = frost.aggregate(sig_shares, commits, msg)
    assert frost.verify(shares[0].group_public_key, msg, sig)


def test_frost_signature_rejects_wrong_message() -> None:
    shares = frost.keygen(n=4, t=3)
    active = shares[:3]
    nonces = [frost.commit_nonces(s.index) for s in active]
    commits = [c for c, _ in nonces]
    witnesses = [w for _, w in nonces]
    sig_shares = [
        frost.sign_share(s, w, b"original", commits) for s, w in zip(active, witnesses, strict=True)
    ]
    sig = frost.aggregate(sig_shares, commits, b"original")
    assert not frost.verify(shares[0].group_public_key, b"tampered", sig)


def test_frost_works_with_different_signer_subsets() -> None:
    """The same group key validates signatures from ANY t-subset."""
    shares = frost.keygen(n=6, t=4)
    for subset in (shares[:4], shares[2:6], [shares[0], shares[1], shares[3], shares[5]]):
        nonces = [frost.commit_nonces(s.index) for s in subset]
        commits = [c for c, _ in nonces]
        witnesses = [w for _, w in nonces]
        msg = b"penumbra-frost-subset"
        sig_shares = [
            frost.sign_share(s, w, msg, commits) for s, w in zip(subset, witnesses, strict=True)
        ]
        sig = frost.aggregate(sig_shares, commits, msg)
        assert frost.verify(shares[0].group_public_key, msg, sig)


def test_frost_rejects_invalid_threshold() -> None:
    with pytest.raises(frost.FROSTError):
        frost.keygen(n=3, t=5)


def test_frost_demo_returns_expected_shape() -> None:
    d = frost.demo(n=4, t=3)
    assert d["available"] is True
    assert d["honest_verifies"] is True
    assert d["tampered_message_verifies"] is False
    assert d["tampered_signature_verifies"] is False
