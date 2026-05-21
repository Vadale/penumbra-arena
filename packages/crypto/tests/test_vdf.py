"""Tests for the Wesolowski VDF."""

from __future__ import annotations

import secrets

import pytest
from penumbra_crypto import vdf


def _random_input() -> int:
    """A non-trivial group element to use as a VDF input."""
    # 2..p-2 to avoid the identity.
    return secrets.randbelow(2**128) + 2


def test_eval_is_deterministic() -> None:
    x = _random_input()
    assert vdf.evaluate(x, 64) == vdf.evaluate(x, 64)


def test_prove_verify_roundtrip_short_delay() -> None:
    x = _random_input()
    ev = vdf.prove(x, delay=128)
    assert vdf.verify(ev)


def test_verify_rejects_tampered_y() -> None:
    x = _random_input()
    ev = vdf.prove(x, delay=64)
    bad = vdf.VDFEvaluation(x=ev.x, y=(ev.y + 1) % (1 << 256), proof=ev.proof, delay=ev.delay)
    assert not vdf.verify(bad)


def test_verify_rejects_tampered_proof() -> None:
    x = _random_input()
    ev = vdf.prove(x, delay=64)
    bad = vdf.VDFEvaluation(x=ev.x, y=ev.y, proof=(ev.proof + 1), delay=ev.delay)
    assert not vdf.verify(bad)


def test_verify_rejects_wrong_delay() -> None:
    x = _random_input()
    ev = vdf.prove(x, delay=64)
    bad = vdf.VDFEvaluation(x=ev.x, y=ev.y, proof=ev.proof, delay=ev.delay + 1)
    assert not vdf.verify(bad)


def test_zero_input_rejected() -> None:
    with pytest.raises(ValueError, match="x must be in"):
        vdf.evaluate(0, 8)


@pytest.mark.slow
def test_eval_with_moderate_delay() -> None:
    """A delay of 2^14 squarings completes in well under 2 seconds on M4."""
    x = _random_input()
    ev = vdf.prove(x, delay=16_384)
    assert vdf.verify(ev)
