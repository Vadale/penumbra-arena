"""Tests for BBS+ selective-disclosure signatures."""

from __future__ import annotations

import pytest
from penumbra_crypto import bbs_plus


def test_bbs_signature_verifies_on_full_vector() -> None:
    keypair, params = bbs_plus.setup(n_messages=4)
    messages = [11, 22, 33, 44]
    sig = bbs_plus.sign(keypair, params, messages)
    assert bbs_plus.verify(params, messages, sig)


def test_bbs_rejects_tampered_message() -> None:
    keypair, params = bbs_plus.setup(n_messages=3)
    messages = [1, 2, 3]
    sig = bbs_plus.sign(keypair, params, messages)
    assert not bbs_plus.verify(params, [1, 2, 999], sig)


def test_bbs_selective_disclosure_keeps_shape() -> None:
    keypair, params = bbs_plus.setup(n_messages=5)
    messages = [10, 20, 30, 40, 50]
    sig = bbs_plus.sign(keypair, params, messages)
    disclosure = bbs_plus.prove(params, messages, sig, [0, 2, 4])
    assert disclosure.disclosed == {0: 10, 2: 30, 4: 50}
    assert disclosure.total_messages == 5
    assert bbs_plus.verify_disclosure(params, disclosure, messages)


def test_bbs_disclosure_with_wrong_values_rejected() -> None:
    keypair, params = bbs_plus.setup(n_messages=4)
    messages = [7, 8, 9, 10]
    sig = bbs_plus.sign(keypair, params, messages)
    disclosure = bbs_plus.prove(params, messages, sig, [1, 3])
    bad = bbs_plus.BBSDisclosure(
        signature=sig,
        disclosed={1: 999, 3: 10},
        total_messages=4,
    )
    assert not bbs_plus.verify_disclosure(params, bad, messages)
    assert bbs_plus.verify_disclosure(params, disclosure, messages)


def test_bbs_rejects_invalid_indices() -> None:
    keypair, params = bbs_plus.setup(n_messages=3)
    messages = [1, 2, 3]
    sig = bbs_plus.sign(keypair, params, messages)
    with pytest.raises(bbs_plus.BBSError):
        bbs_plus.prove(params, messages, sig, [5])


def test_bbs_demo() -> None:
    d = bbs_plus.demo(n_messages=4)
    assert d["available"] is True
    assert d["honest_signature_verifies"] is True
    assert d["tampered_message_verifies"] is False
    assert d["disclosure_verifies"] is True
    assert d["tampered_disclosure_verifies"] is False
