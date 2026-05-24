"""Tests for BLS aggregate signatures and Schnorr-VRF."""

from __future__ import annotations

from penumbra_crypto import bls, vrf

# ── BLS ───────────────────────────────────────────────────────────


def test_bls_sign_verify_roundtrip() -> None:
    kp = bls.keygen()
    sig = bls.sign(kp.secret_key, b"penumbra block 1")
    assert bls.verify(kp.public_key, b"penumbra block 1", sig)


def test_bls_rejects_wrong_message() -> None:
    kp = bls.keygen()
    sig = bls.sign(kp.secret_key, b"correct")
    assert not bls.verify(kp.public_key, b"wrong", sig)


def test_bls_rejects_wrong_pubkey() -> None:
    a = bls.keygen()
    b = bls.keygen()
    sig = bls.sign(a.secret_key, b"x")
    assert not bls.verify(b.public_key, b"x", sig)


def test_bls_aggregate_then_fast_verify() -> None:
    """5 validators sign the same block; aggregate verifies against the pubkey set."""
    validators = [bls.keygen() for _ in range(5)]
    message = b"penumbra block-finality"
    sigs = [bls.sign(v.secret_key, message) for v in validators]
    aggregate = bls.aggregate_signatures(sigs)
    pks = [v.public_key for v in validators]
    assert bls.fast_aggregate_verify(pks, message, aggregate)


def test_bls_aggregate_rejects_tampered_signer() -> None:
    """If one signer's sig is replaced with garbage, the aggregate fails."""
    validators = [bls.keygen() for _ in range(3)]
    message = b"penumbra block"
    sigs = [bls.sign(v.secret_key, message) for v in validators]
    # Tamper the last signature with a sig from a *different* validator on a
    # *different* message — clearly invalid in the aggregate context.
    foreign = bls.keygen()
    sigs[-1] = bls.sign(foreign.secret_key, b"other message")
    bad_aggregate = bls.aggregate_signatures(sigs)
    pks = [v.public_key for v in validators]
    assert not bls.fast_aggregate_verify(pks, message, bad_aggregate)


def test_bls_proof_of_possession_roundtrip() -> None:
    kp = bls.keygen()
    pop = bls.prove_possession(kp.secret_key)
    assert bls.verify_possession(kp.public_key, pop)


def test_bls_pop_is_specific_to_owner() -> None:
    """A PoP made with one secret key must NOT verify under a different pubkey."""
    a = bls.keygen()
    b = bls.keygen()
    pop_a = bls.prove_possession(a.secret_key)
    assert not bls.verify_possession(b.public_key, pop_a)


def test_bls_aggregate_of_empty_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="zero signatures"):
        bls.aggregate_signatures([])


def test_bls_key_sizes_match_spec() -> None:
    kp = bls.keygen()
    assert len(kp.public_key) == bls.PUBLIC_KEY_BYTES
    sig = bls.sign(kp.secret_key, b"x")
    assert len(sig) == bls.SIGNATURE_BYTES


def test_wipe_zeroes_bytearray() -> None:
    """Crypto-audit closure: a mutable bytearray is fully zeroed in place."""
    secret = bytearray(b"\x01\x02\x03\x04\x05\x06\x07\x08")
    bls.wipe(secret)
    assert bytes(secret) == b"\x00" * 8


def test_wipe_on_bytes_is_noop_and_does_not_raise() -> None:
    """``wipe(bytes)`` documents the limitation but must not error."""
    immutable = b"\xde\xad\xbe\xef"
    bls.wipe(immutable)
    assert immutable == b"\xde\xad\xbe\xef"


# ── VRF ───────────────────────────────────────────────────────────


def test_vrf_prove_verify_roundtrip() -> None:
    kp = vrf.keygen()
    output = vrf.prove(kp.secret_key, b"block-42-seed")
    assert vrf.verify(kp.public_key, b"block-42-seed", output)


def test_vrf_output_is_deterministic() -> None:
    """Same (sk, alpha) -> same beta. Different randomness in the proof
    transcript is fine; what counts is the output bytes."""
    kp = vrf.keygen()
    a = vrf.prove(kp.secret_key, b"alpha")
    b = vrf.prove(kp.secret_key, b"alpha")
    assert a.beta == b.beta


def test_vrf_different_alphas_diverge() -> None:
    kp = vrf.keygen()
    a = vrf.prove(kp.secret_key, b"alpha-1")
    b = vrf.prove(kp.secret_key, b"alpha-2")
    assert a.beta != b.beta


def test_vrf_rejects_wrong_pubkey() -> None:
    a = vrf.keygen()
    b = vrf.keygen()
    output = vrf.prove(a.secret_key, b"alpha")
    assert not vrf.verify(b.public_key, b"alpha", output)


def test_vrf_rejects_wrong_alpha() -> None:
    kp = vrf.keygen()
    output = vrf.prove(kp.secret_key, b"alpha")
    assert not vrf.verify(kp.public_key, b"other-alpha", output)


def test_vrf_rejects_tampered_beta() -> None:
    kp = vrf.keygen()
    output = vrf.prove(kp.secret_key, b"alpha")
    tampered = vrf.VRFOutput(beta=b"\x00" * 32, proof=output.proof)
    assert not vrf.verify(kp.public_key, b"alpha", tampered)


def test_vrf_rejects_tampered_proof() -> None:
    kp = vrf.keygen()
    output = vrf.prove(kp.secret_key, b"alpha")
    bad = vrf.VRFOutput(
        beta=output.beta,
        proof=vrf.VRFProof(gamma=output.proof.gamma, c=output.proof.c, s=output.proof.s + 1),
    )
    assert not vrf.verify(kp.public_key, b"alpha", bad)


def test_vrf_leader_election_use_case() -> None:
    """5 validators, each VRF-derive a score for block N; the lowest wins."""
    seed = b"penumbra-block-123-seed"
    validators = [vrf.keygen() for _ in range(5)]
    outputs = [vrf.prove(v.secret_key, seed) for v in validators]
    scores = [int.from_bytes(o.beta, "big") for o in outputs]
    leader = scores.index(min(scores))
    # Every other validator can verify the leader's claim.
    assert vrf.verify(validators[leader].public_key, seed, outputs[leader])
