"""Tests for the educational FRI-STARK verifier."""

from __future__ import annotations

import pytest
from penumbra_crypto import stark
from penumbra_crypto.stark import (
    FRIRound,
    STARKError,
    STARKProof,
    demo,
    merkle_open,
    merkle_root,
    merkle_verify,
    prove,
    serialise_proof,
    verify,
)

# ── Merkle tree primitives ───────────────────────────────────────


def test_merkle_root_deterministic() -> None:
    leaves = [b"a", b"b", b"c", b"d"]
    assert merkle_root(leaves) == merkle_root(leaves)


def test_merkle_open_and_verify_round_trip() -> None:
    leaves = [bytes([i] * 4) for i in range(8)]
    root = merkle_root(leaves)
    for i in range(8):
        proof = merkle_open(leaves, i)
        assert merkle_verify(root, proof) is True


def test_merkle_verify_rejects_tampered_leaf() -> None:
    leaves = [bytes([i] * 4) for i in range(4)]
    root = merkle_root(leaves)
    proof = merkle_open(leaves, 1)
    bad = type(proof)(leaf=b"\x00\x00\x00\xff", path=proof.path, index=proof.index)
    assert merkle_verify(root, bad) is False


def test_merkle_open_out_of_range_raises() -> None:
    with pytest.raises(STARKError):
        merkle_open([b"only"], 5)


# ── STARK verifier ───────────────────────────────────────────────


def test_honest_proof_verifies() -> None:
    coeffs = [3, 1, 4, 1, 5, 9, 2, 6]
    proof = prove(coeffs)
    assert verify(proof) is True


def test_tampered_evaluation_rejected() -> None:
    coeffs = [11, 22, 33, 44]
    proof = prove(coeffs)
    bad_round = FRIRound(
        commitment=proof.fri_proof[0].commitment,
        queried_left=(proof.fri_proof[0].queried_left + 1) % 998_244_353,
        queried_right=proof.fri_proof[0].queried_right,
        proof_left=proof.fri_proof[0].proof_left,
        proof_right=proof.fri_proof[0].proof_right,
    )
    tampered = STARKProof(
        commitments=proof.commitments,
        evaluations=proof.evaluations,
        fri_proof=(bad_round, *proof.fri_proof[1:]),
        final_constant=proof.final_constant,
        query_index=proof.query_index,
        domain_size=proof.domain_size,
        initial_degree_bound=proof.initial_degree_bound,
    )
    assert verify(tampered) is False


def test_tampered_commitment_rejected() -> None:
    coeffs = [7, 8, 9, 10, 11, 12, 13, 14]
    proof = prove(coeffs)
    bad_commit = bytes([proof.commitments[0][0] ^ 1, *proof.commitments[0][1:]])
    tampered = STARKProof(
        commitments=(bad_commit, *proof.commitments[1:]),
        evaluations=proof.evaluations,
        fri_proof=proof.fri_proof,
        final_constant=proof.final_constant,
        query_index=proof.query_index,
        domain_size=proof.domain_size,
        initial_degree_bound=proof.initial_degree_bound,
    )
    assert verify(tampered) is False


def test_tampered_final_constant_rejected() -> None:
    coeffs = [1, 2, 3, 4]
    proof = prove(coeffs)
    tampered = STARKProof(
        commitments=proof.commitments,
        evaluations=proof.evaluations,
        fri_proof=proof.fri_proof,
        final_constant=(proof.final_constant + 1) % 998_244_353,
        query_index=proof.query_index,
        domain_size=proof.domain_size,
        initial_degree_bound=proof.initial_degree_bound,
    )
    assert verify(tampered) is False


def test_empty_proof_rejected() -> None:
    empty = STARKProof(
        commitments=(),
        evaluations=(),
        fri_proof=(),
        final_constant=0,
        query_index=0,
        domain_size=8,
        initial_degree_bound=1,
    )
    assert verify(empty) is False


def test_swapped_commitments_rejected() -> None:
    coeffs = [5, 5, 5, 5, 5, 5, 5, 5]
    proof = prove(coeffs)
    # Swap commitment between round 0 and 1 (but keep merkle proofs in
    # the round); verifier links each round's commitment to its merkle
    # auth path so the swap must be detected.
    swapped = STARKProof(
        commitments=(proof.commitments[1], proof.commitments[0], *proof.commitments[2:]),
        evaluations=proof.evaluations,
        fri_proof=proof.fri_proof,
        final_constant=proof.final_constant,
        query_index=proof.query_index,
        domain_size=proof.domain_size,
        initial_degree_bound=proof.initial_degree_bound,
    )
    assert verify(swapped) is False


def test_bad_domain_size_rejected() -> None:
    proof = prove([1, 2, 3, 4])
    bad = STARKProof(
        commitments=proof.commitments,
        evaluations=proof.evaluations,
        fri_proof=proof.fri_proof,
        final_constant=proof.final_constant,
        query_index=proof.query_index,
        domain_size=24,  # not a power of two
        initial_degree_bound=proof.initial_degree_bound,
    )
    assert verify(bad) is False


def test_prove_rejects_empty_coeffs() -> None:
    with pytest.raises(STARKError):
        prove([])


def test_demo_payload_shape() -> None:
    payload = demo()
    assert payload["available"] is True
    assert payload["honest_verifies"] is True
    assert payload["tampered_evaluation_verifies"] is False
    assert payload["tampered_commitment_verifies"] is False
    assert isinstance(payload["domain_size"], int)
    assert isinstance(payload["n_fri_rounds"], int)


def test_serialise_proof_round_trips_to_json() -> None:
    import json

    proof = prove([1, 0, 0, 1])
    blob = serialise_proof(proof)
    parsed = json.loads(blob)
    assert "commitments" in parsed
    assert "fri_proof" in parsed
    assert parsed["domain_size"] == proof.domain_size


def test_verify_uses_constant_domain_for_different_coeffs() -> None:
    """Two proofs of different polynomials each verify independently."""
    p1 = prove([1, 2, 3, 4])
    p2 = prove([5, 6, 7, 8, 9, 10, 11, 12])
    assert verify(p1) is True
    assert verify(p2) is True


def test_stark_module_exports_what_demo_needs() -> None:
    """Spot check the public surface stays accessible to the dashboard."""
    assert hasattr(stark, "demo")
    assert hasattr(stark, "verify")
    assert hasattr(stark, "prove")
    assert hasattr(stark, "STARKProof")
