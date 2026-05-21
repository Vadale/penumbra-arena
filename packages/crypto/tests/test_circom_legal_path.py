"""End-to-end test for the real Groth16 'legal-path' circuit.

The artifacts under `circuits/artifacts/legal_path_*.json` were
produced by:
    cd circuits && bash setup_legal_path.sh

The circuit proves "I know an intermediate node `mid` such that
(start, mid) and (mid, goal) are both edges in the published 4×4
arena adjacency bitmap" — a real semantic ZK proof of a legal walk
through the arena, no synthetic fixture.

The path baked into the artifacts goes 0 → 2 → 3 on this graph:

    0 ── 1
    │ ╲  │
    2 ── 3   (so edges: 0-1, 0-2, 0-3? — see inputs/legal_path_sample.json)

What matters for the test: our pure-Python Groth16 verifier accepts
the snarkjs-generated proof under the published 18 public inputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from penumbra_crypto.snark import load_proof, load_verifying_key, verify

_ARTIFACTS = Path(__file__).resolve().parents[3] / "circuits" / "artifacts"


@pytest.fixture(scope="module")
def artifacts() -> tuple[object, object, list[int]]:
    vk_path = _ARTIFACTS / "legal_path_vk.json"
    proof_path = _ARTIFACTS / "legal_path_proof.json"
    public_path = _ARTIFACTS / "legal_path_public.json"
    if not vk_path.is_file() or not proof_path.is_file() or not public_path.is_file():
        msg = f"legal_path snarkjs artifacts not found at {_ARTIFACTS}."
        pytest.skip(f"{msg} Run `cd circuits && bash setup_legal_path.sh` first.")
    vk = load_verifying_key(json.loads(vk_path.read_text()))
    proof = load_proof(json.loads(proof_path.read_text()))
    public = [int(s) for s in json.loads(public_path.read_text())]
    return vk, proof, public


def test_legal_path_proof_verifies(artifacts: tuple[object, object, list[int]]) -> None:
    """A genuine ZK proof of 'I know a legal 2-hop walk' must verify."""
    vk, proof, public = artifacts
    assert len(public) == 18  # 16 adjacency bits + start + goal
    # Public input layout sanity:
    # - last two are start (0) and goal (3) for the shipped sample
    assert public[-2] == 0
    assert public[-1] == 3
    assert verify(vk, proof, public)  # type: ignore[arg-type]


def test_legal_path_rejects_tampered_goal(
    artifacts: tuple[object, object, list[int]],
) -> None:
    """Claiming the path ended at a different node breaks the binding."""
    vk, proof, public = artifacts
    tampered = [*public[:-1], 1]  # claim goal=1 instead of 3
    assert not verify(vk, proof, tampered)  # type: ignore[arg-type]


def test_legal_path_rejects_tampered_adjacency(
    artifacts: tuple[object, object, list[int]],
) -> None:
    """Flipping an adjacency bit changes the verification key inputs and breaks the proof."""
    vk, proof, public = artifacts
    tampered = list(public)
    # Flip adj[5] (a 0 in the published graph becomes a 1)
    tampered[5] = 1 - tampered[5]
    assert not verify(vk, proof, tampered)  # type: ignore[arg-type]
