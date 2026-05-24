"""Groth16 zk-SNARK verifier — pure Python over BN128 pairings.

Concept taught: a Groth16 proof is *three group elements* and the
verifier's whole job is to evaluate **one pairing equation**:

    e(A, B) · e(α, β)⁻¹ · e(IC, γ)⁻¹ · e(C, δ)⁻¹  ?=  1

where:
- (A, B, C) is the proof — A, C ∈ G1; B ∈ G2;
- (α, β, γ, δ) are part of the trusted-setup verifying key;
- IC is `IC_0 + Σ_{i≥1} public_input[i-1] · IC_i`, a public-input
  commitment built from the verifying key.

Three pairings means O(1) constant verifier time regardless of the
underlying circuit size — that's the magic.

Positive-case integration
-------------------------
Generating a real Groth16 proof requires a Rank-1 Constraint System
+ QAP + trusted setup + prover — far more code than the verifier
itself. The intended workflow:

  1. Write the circuit in circom:           `circuit.circom`
  2. Compile, setup, prove with snarkjs:
       circom circuit.circom --r1cs --wasm
       snarkjs groth16 setup circuit.r1cs ptau key.zkey
       snarkjs zkey export verificationkey key.zkey vk.json
       snarkjs groth16 prove key.zkey witness.wtns proof.json public.json
  3. Load the resulting JSON into Penumbra:
       vk = load_verifying_key(json.load(open("vk.json")))
       proof = load_proof(json.load(open("proof.json")))
       public = [int(x) for x in json.load(open("public.json"))]
       verify(vk, proof, public)            # → True / False

References
- Groth, "On the size of pairing-based non-interactive arguments"
  (EUROCRYPT 2016). The original paper.
- snarkjs spec: https://github.com/iden3/snarkjs
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from py_ecc.bn128 import FQ12, add, multiply, neg, pairing
from py_ecc.bn128.bn128_curve import b, b2, is_on_curve
from py_ecc.bn128.bn128_curve import curve_order as CURVE_ORDER  # noqa: N812

# py_ecc.bn128 returns concrete Point2D[bn128_FQ] / Point2D[bn128_FQ2] tuples
# at runtime but the stubs make them awkward to name; we use Any so the
# verifier reads cleanly while still passing the points through unchanged.
G1Point = Any
G2Point = Any


@dataclass(frozen=True, slots=True)
class VerifyingKey:
    """Groth16 verifying key (a.k.a. vk.json from snarkjs)."""

    alpha_g1: G1Point
    beta_g2: G2Point
    gamma_g2: G2Point
    delta_g2: G2Point
    ic: tuple[G1Point, ...]  # ic[0] + Σ public_input_i · ic[i+1]


@dataclass(frozen=True, slots=True)
class Proof:
    a: G1Point
    b: G2Point
    c: G1Point


def verify(vk: VerifyingKey, proof: Proof, public_inputs: list[int]) -> bool:
    """Evaluate the Groth16 pairing equation. Returns True iff the proof is valid."""
    if len(public_inputs) + 1 != len(vk.ic):
        return False  # public-input count mismatch with the verifying key
    if not _is_valid_g1(proof.a):
        return False
    if not _is_valid_g2(proof.b):
        return False
    if not _is_valid_g1(proof.c):
        return False
    if any(not 0 <= x < CURVE_ORDER for x in public_inputs):
        return False

    # IC = vk.ic[0] + Σ public_inputs[i] · vk.ic[i+1]
    ic_acc = vk.ic[0]
    for i, public in enumerate(public_inputs):
        ic_acc = add(ic_acc, multiply(vk.ic[i + 1], public))

    # Check  e(A, B) = e(α, β) · e(IC, γ) · e(C, δ)
    # ⇔     e(A, B) · e(-α, β) · e(-IC, γ) · e(-C, δ) = 1
    lhs = pairing(proof.b, proof.a)
    factor_alpha = pairing(vk.beta_g2, neg(vk.alpha_g1))
    factor_ic = pairing(vk.gamma_g2, neg(ic_acc))
    factor_c = pairing(vk.delta_g2, neg(proof.c))
    product = lhs * factor_alpha * factor_ic * factor_c
    return product == FQ12.one()


# ── snarkjs-format JSON loaders ──────────────────────────────────


def load_verifying_key(payload: dict[str, Any]) -> VerifyingKey:
    """Convert a snarkjs vk.json dict into a `VerifyingKey`."""
    return VerifyingKey(
        alpha_g1=_g1_from_json(payload["vk_alpha_1"]),
        beta_g2=_g2_from_json(payload["vk_beta_2"]),
        gamma_g2=_g2_from_json(payload["vk_gamma_2"]),
        delta_g2=_g2_from_json(payload["vk_delta_2"]),
        ic=tuple(_g1_from_json(point) for point in payload["IC"]),
    )


def load_proof(payload: dict[str, Any]) -> Proof:
    """Convert a snarkjs proof.json dict into a `Proof`."""
    return Proof(
        a=_g1_from_json(payload["pi_a"]),
        b=_g2_from_json(payload["pi_b"]),
        c=_g1_from_json(payload["pi_c"]),
    )


# ── internals ────────────────────────────────────────────────────


def _is_valid_g1(point: G1Point) -> bool:
    try:
        return is_on_curve(point, b)
    except Exception:
        return False


def _is_valid_g2(point: G2Point) -> bool:
    """Validate a G2 point: twist-curve equation AND prime-order subgroup.

    Crypto-audit closure: previously this only verified the twist curve
    equation. The BN128 G2 cofactor is ~10^76, so a small-subgroup
    attacker could craft a point that lies on the twist but outside the
    prime-order subgroup, weakening the Groth16 security reduction.
    The fix follows Wu et al. 2022 — multiply by the curve order; the
    result must be the identity at infinity for genuine subgroup points.
    """
    try:
        if not is_on_curve(point, b2):
            return False
        return multiply(point, CURVE_ORDER) is None
    except Exception:
        return False


def _g1_from_json(coords: list[Any]) -> G1Point:
    """snarkjs writes G1 points as [x, y, 1] projective; we read affine x,y."""
    from py_ecc.bn128.bn128_curve import FQ

    return (FQ(int(coords[0])), FQ(int(coords[1])))


def _g2_from_json(coords: list[Any]) -> G2Point:
    """snarkjs G2: nested [[x0, x1, …], [y0, y1, …], …]; we read affine x, y in FQ2."""
    from py_ecc.bn128.bn128_curve import FQ2

    return (
        FQ2([int(coords[0][0]), int(coords[0][1])]),
        FQ2([int(coords[1][0]), int(coords[1][1])]),
    )
