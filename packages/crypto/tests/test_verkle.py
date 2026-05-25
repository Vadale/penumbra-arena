"""Tests for the Verkle (KZG) verifier + proof-size comparison."""

from __future__ import annotations

import pytest
from penumbra_crypto import verkle


def test_kzg_honest_open_verifies() -> None:
    setup = verkle.setup(max_degree=4)
    coeffs = [1, 2, 3, 4, 5]
    commitment = verkle.commit(setup, coeffs)
    proof = verkle.open_proof(setup, coeffs, z=7)
    assert verkle.verify(setup, commitment, proof)


def test_kzg_tampered_y_rejects() -> None:
    setup = verkle.setup(max_degree=4)
    coeffs = [3, 1, 4, 1, 5]
    commitment = verkle.commit(setup, coeffs)
    proof = verkle.open_proof(setup, coeffs, z=11)
    tampered = verkle.KZGProof(z=proof.z, y=(proof.y + 1), pi=proof.pi)
    assert not verkle.verify(setup, commitment, tampered)


@pytest.mark.slow
def test_kzg_random_polynomials_roundtrip() -> None:
    """Marked `slow`: 34 s — 5 fresh KZG setups + commit/open/verify
    rounds over pairing-heavy BLS12-381 operations."""
    setup = verkle.setup(max_degree=6)
    import secrets

    for _ in range(5):
        coeffs = [secrets.randbelow(2**32) for _ in range(7)]
        commitment = verkle.commit(setup, coeffs)
        z = secrets.randbelow(2**32)
        proof = verkle.open_proof(setup, coeffs, z)
        assert verkle.verify(setup, commitment, proof)


def test_verkle_proof_size_beats_merkle_at_large_n() -> None:
    d = verkle.demo(n_leaves=1_000_000)
    assert int(d["merkle_proof_bytes"]) > int(d["verkle_proof_bytes"])  # type: ignore[arg-type]
    assert float(d["compression_ratio"]) >= 1.0  # type: ignore[arg-type]


def test_verkle_setup_rejects_too_large_polynomials() -> None:
    setup = verkle.setup(max_degree=3)
    with pytest.raises(verkle.VerkleError):
        verkle.commit(setup, [1, 2, 3, 4, 5, 6])


def test_verkle_demo() -> None:
    d = verkle.demo()
    assert d["available"] is True
    assert d["honest_verifies"] is True
    assert d["tampered_y_verifies"] is False
