"""Property and unit tests for the educational SMPC + ZK primitives."""

from __future__ import annotations

import secrets

import pytest
from penumbra_crypto.educational import beaver, pedersen, schnorr, shamir

# ── Shamir ────────────────────────────────────────────────────────


def test_shamir_threshold_reconstruction() -> None:
    secret = 0xCAFEBABE_DEADBEEF
    shares = shamir.split(secret, n=5, t=3)
    assert shamir.reconstruct(shares[:3]) == secret
    assert shamir.reconstruct(shares[2:5]) == secret


def test_shamir_full_set_also_reconstructs() -> None:
    secret = 42
    shares = shamir.split(secret, n=5, t=3)
    assert shamir.reconstruct(shares) == secret


def test_shamir_too_few_shares_misses() -> None:
    """With t-1 shares the reconstruction lands at some unrelated field element."""
    secret = 0xC0FFEE
    shares = shamir.split(secret, n=5, t=3)
    bad = shamir.reconstruct(shares[:2])
    assert bad != secret  # negligible probability of collision in 2^256 field


def test_shamir_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError, match="t <= n"):
        shamir.split(1, n=3, t=5)


def test_shamir_rejects_duplicate_shares() -> None:
    shares = shamir.split(123, n=4, t=2)
    with pytest.raises(ValueError, match="duplicate"):
        shamir.reconstruct([shares[0], shares[0]])


# ── Beaver ────────────────────────────────────────────────────────


def test_beaver_triple_multiplies_correctly() -> None:
    """Sanity: c = a*b in the triple."""
    triple = beaver.generate_triple(n_parties=3)
    a = beaver.reconstruct_sum(triple.a_shares)
    b = beaver.reconstruct_sum(triple.b_shares)
    c = beaver.reconstruct_sum(triple.c_shares)
    assert (a * b) % shamir.field_modulus() == c


def test_beaver_multiply_recovers_product() -> None:
    n = 4
    triple = beaver.generate_triple(n_parties=n)
    p = shamir.field_modulus()
    x_secret = 12345
    y_secret = 6789

    x_shares = tuple([secrets.randbelow(p) for _ in range(n - 1)])
    x_shares = (*x_shares, (x_secret - sum(x_shares)) % p)
    y_shares = tuple([secrets.randbelow(p) for _ in range(n - 1)])
    y_shares = (*y_shares, (y_secret - sum(y_shares)) % p)

    z_shares = beaver.beaver_multiply(x_shares, y_shares, triple)
    assert beaver.reconstruct_sum(z_shares) == (x_secret * y_secret) % p


def test_beaver_rejects_mismatched_widths() -> None:
    triple = beaver.generate_triple(n_parties=3)
    with pytest.raises(ValueError, match="match the triple width"):
        beaver.beaver_multiply((1, 2), (1, 2, 3), triple)


# ── Pedersen ──────────────────────────────────────────────────────


def test_pedersen_commit_open_roundtrip() -> None:
    c, opening = pedersen.commit(42)
    assert pedersen.verify(c, opening)


def test_pedersen_wrong_message_fails() -> None:
    c, opening = pedersen.commit(42)
    wrong = pedersen.Opening(message=43, blinding=opening.blinding)
    assert not pedersen.verify(c, wrong)


def test_pedersen_wrong_blinding_fails() -> None:
    c, opening = pedersen.commit(42)
    wrong = pedersen.Opening(message=opening.message, blinding=opening.blinding + 1)
    assert not pedersen.verify(c, wrong)


def test_pedersen_explicit_blinding_is_honoured() -> None:
    c1, _ = pedersen.commit(42, blinding=999)
    c2, _ = pedersen.commit(42, blinding=999)
    assert c1.value == c2.value  # deterministic given the same blinding


def test_pedersen_two_random_commitments_to_same_message_differ() -> None:
    c1, _ = pedersen.commit(42)
    c2, _ = pedersen.commit(42)
    assert c1.value != c2.value  # negligible probability of identical r


# ── Schnorr ───────────────────────────────────────────────────────


def test_schnorr_proof_verifies() -> None:
    witness, statement = schnorr.keygen()
    proof = schnorr.prove(witness, statement)
    assert schnorr.verify(statement, proof)


def test_schnorr_proof_rejected_with_wrong_witness() -> None:
    _, statement = schnorr.keygen()
    other_witness, _ = schnorr.keygen()
    with pytest.raises(ValueError, match="witness does not match"):
        schnorr.prove(other_witness, statement)


def test_schnorr_proof_rejected_after_tamper() -> None:
    witness, statement = schnorr.keygen()
    proof = schnorr.prove(witness, statement)
    tampered = schnorr.Proof(t=proof.t, s=proof.s + 1, c=proof.c)
    assert not schnorr.verify(statement, tampered)


def test_schnorr_context_binding() -> None:
    """A proof built for one context must not verify under another."""
    witness, statement = schnorr.keygen()
    proof = schnorr.prove(witness, statement, context=b"context-A")
    assert schnorr.verify(statement, proof, context=b"context-A")
    assert not schnorr.verify(statement, proof, context=b"context-B")


def test_schnorr_replayed_proof_under_other_statement_fails() -> None:
    """Reusing a proof against a different y must not verify (the
    challenge is bound to y in the transcript)."""
    w1, s1 = schnorr.keygen()
    _, s2 = schnorr.keygen()
    proof = schnorr.prove(w1, s1)
    assert not schnorr.verify(s2, proof)
