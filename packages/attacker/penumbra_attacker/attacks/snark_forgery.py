"""SNARK forgery: try to fake a Groth16 proof without a witness.

Concept taught: zero-knowledge SOUNDNESS. A Groth16 proof is a triple
(A, B, C) ∈ G1 × G2 × G1 that satisfies one pairing equation against
the verifying key and the public inputs. Without the witness, the
prover cannot construct (A, B, C) that satisfies it — the pairing
check is the soundness guarantee.

This module ships TWO forgery attempts to demonstrate that the
verifier rejects both:

1. **Random-bytes forgery** — sample three random G1/G2 points and
   wire them into a Proof. Verifier rejects: the pairing equation
   doesn't hold by overwhelming probability.

2. **Replay with wrong public inputs** — take a real proof and submit
   it against TAMPERED public inputs. Verifier rejects: Groth16
   proofs bind to their public inputs (they're folded into the
   linear combination on the verifier's side).

The "defence" doc lives in the docstring you're reading: the proof
SOUNDNESS is what stops the forger, not any external service.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from penumbra_crypto.snark import load_proof, load_verifying_key, verify


def _resolve_artifacts() -> Path:
    """Find the circom artifacts directory.

    Resolution order:
    1. PENUMBRA_ARTIFACTS_DIR env var (explicit override).
    2. ./circuits/artifacts relative to cwd (repo-root server case).
    3. Walk up from this file looking for circuits/artifacts (dev case).
    """
    env_dir = os.environ.get("PENUMBRA_ARTIFACTS_DIR")
    if env_dir:
        return Path(env_dir)
    cwd_candidate = Path.cwd() / "circuits" / "artifacts"
    if cwd_candidate.is_dir():
        return cwd_candidate
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "circuits" / "artifacts"
        if candidate.is_dir():
            return candidate
    return Path.cwd() / "circuits" / "artifacts"


@dataclass(frozen=True, slots=True)
class ForgeryResult:
    """Result of one forgery attempt."""

    random_forge_accepted: bool
    replay_with_tampered_inputs_accepted: bool
    honest_proof_accepted: bool


def demo(artifacts_dir: Path | None = None) -> ForgeryResult:
    """Attempt two forgeries against the shipped Groth16 verifying key.

    Returns a ForgeryResult; the verifier should REJECT both forgeries
    while still ACCEPTing the honest reference proof.
    """
    art = artifacts_dir or _resolve_artifacts()
    vk_path = art / "legal_path_vk.json"
    proof_path = art / "legal_path_proof.json"
    public_path = art / "legal_path_public.json"
    if not all(p.is_file() for p in (vk_path, proof_path, public_path)):
        raise FileNotFoundError(f"Groth16 artifacts not found under {art}; run circuits/setup.sh")

    vk = load_verifying_key(json.loads(vk_path.read_text()))
    honest_proof = load_proof(json.loads(proof_path.read_text()))
    public = [int(s) for s in json.loads(public_path.read_text())]

    # 1. Honest proof — should accept.
    honest_ok = verify(vk, honest_proof, public)

    # 2. Random-bytes forgery — fabricate a Proof from random G1/G2.
    forged = _random_garbage_proof(honest_proof)
    random_ok = verify(vk, forged, public)  # type: ignore[arg-type]

    # 3. Replay-with-tampered-inputs — take the honest proof, submit
    # it against modified public inputs.
    tampered_public = list(public)
    tampered_public[-1] = (tampered_public[-1] + 1) % 4
    replay_ok = verify(vk, honest_proof, tampered_public)

    return ForgeryResult(
        random_forge_accepted=bool(random_ok),
        replay_with_tampered_inputs_accepted=bool(replay_ok),
        honest_proof_accepted=bool(honest_ok),
    )


def _random_garbage_proof(template: object) -> object:
    """Return a Proof with A's x-coordinate flipped — pairing check should reject.

    G1Point is a py_ecc Point2D tuple (FQ(x), FQ(y)), NOT a dataclass.
    We build a fresh tuple with the low bit of x flipped — almost
    certainly off-curve (the EC equation constrains a measure-zero
    subset of Z_p) and the verify path rejects.
    """
    import dataclasses

    from py_ecc.bn128.bn128_curve import FQ

    old_a = template.a  # type: ignore[attr-defined]
    old_x = int(old_a[0])
    old_y = int(old_a[1])
    new_a = (FQ(old_x ^ 1), FQ(old_y))
    return dataclasses.replace(template, a=new_a)  # type: ignore[arg-type]
