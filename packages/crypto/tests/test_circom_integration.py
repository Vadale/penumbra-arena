"""End-to-end Groth16 integration test against snarkjs-generated artifacts.

Loads the vk.json + proof.json + public.json files produced by
`circuits/setup.sh` and verifies them via Penumbra's pure-Python
Groth16 verifier. If the artifacts aren't present (i.e. the user
hasn't run the ceremony yet), the test skips with a clear message.

This closes the "real circom proof" loop: prove the multiplier
3 * 5 = 15 via snarkjs, ship only (vk, proof, public=[15]) to a
verifier that has no idea what circom is — and watch our pairing
equation accept it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from penumbra_crypto.snark import (
    Proof,
    VerifyingKey,
    load_proof,
    load_verifying_key,
    verify,
)

_ARTIFACTS = Path(__file__).resolve().parents[3] / "circuits" / "artifacts"


@pytest.fixture(scope="module")
def artifacts() -> tuple[VerifyingKey, Proof, list[int]]:
    vk_path = _ARTIFACTS / "vk.json"
    proof_path = _ARTIFACTS / "proof.json"
    public_path = _ARTIFACTS / "public.json"
    if not vk_path.is_file() or not proof_path.is_file() or not public_path.is_file():
        msg = f"snarkjs artifacts not found at {_ARTIFACTS}."
        pytest.skip(f"{msg} Run `cd circuits && bash setup.sh` first.")
    vk = load_verifying_key(json.loads(vk_path.read_text()))
    proof = load_proof(json.loads(proof_path.read_text()))
    public_strings = json.loads(public_path.read_text())
    public_inputs = [int(s) for s in public_strings]
    return vk, proof, public_inputs


def test_real_groth16_proof_verifies(artifacts: tuple[VerifyingKey, Proof, list[int]]) -> None:
    vk, proof, public_inputs = artifacts
    # The multiplier circuit asserts 3 * 5 = 15.
    assert public_inputs == [15]
    assert verify(vk, proof, public_inputs)


def test_real_groth16_rejects_tampered_public_input(
    artifacts: tuple[VerifyingKey, Proof, list[int]],
) -> None:
    """If we claim the product is 16 instead of 15, the proof must fail."""
    vk, proof, _ = artifacts
    assert not verify(vk, proof, [16])


def test_real_groth16_rejects_wrong_public_input_count(
    artifacts: tuple[VerifyingKey, Proof, list[int]],
) -> None:
    vk, proof, _ = artifacts
    assert not verify(vk, proof, [])
    assert not verify(vk, proof, [15, 999])
