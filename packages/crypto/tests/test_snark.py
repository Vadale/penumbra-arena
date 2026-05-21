"""Tests for the Groth16 verifier.

The pairing equation itself is exercised against a *synthetic* but
mathematically valid (vk, proof) tuple constructed in-test. This is
the right scope: it confirms the verifier accepts a correct proof and
rejects mutated ones, without dragging in the entire circom + snarkjs
toolchain.

A positive-case integration test against a real snarkjs proof is left
as a "run this externally" docs note — see snark.py module docstring.
"""

from __future__ import annotations

import secrets

from penumbra_crypto.snark import (
    Proof,
    VerifyingKey,
    verify,
)
from py_ecc.bn128 import G1, G2, add, multiply
from py_ecc.bn128.bn128_curve import curve_order as CURVE_ORDER  # noqa: N812


def _build_synthetic_vk_and_proof(
    public_inputs_count: int = 0,
) -> tuple[VerifyingKey, Proof, list[int]]:
    """Construct a vk + proof that satisfies the pairing equation by
    *construction*, with no public inputs by default.

    Trick: pick α=1·G1, β=δ=γ=1·G2 (all identity-style). Then the
    equation reduces to e(A, B) = e(α, β) · e(IC, γ) · e(C, δ) and we
    can set A=α, B=β, IC=neutral, C=neutral so it holds trivially.

    Since the BN128 group has no convenient neutral element handle in
    py_ecc, the most robust construction uses the FACT that:
        e(A, B) · e(-α, β)^{...} ... = 1
    holds if we set A = α + IC + C (in G1, all on the same B in G2),
    α = something, IC=γ=δ=β so e(α, β) e(IC, γ) e(C, δ) factors as
    e(α + IC + C, β).

    Concrete construction
    ---------------------
    Let s ∈ Z_q random. Define:
        α = s · G1               β = G2
        γ = β,  δ = β
        IC = [-s · G1]   (so when public_inputs are empty, ic_acc = IC[0] = -s·G1)
        A  = (s - 1) · G1
        B  = β
        C  = 1 · G1
    Then ic_acc + α + C = (-s + s + 1) · G1 = G1 = A + G1,
    hmm this doesn't quite work out. Let me think again.

    Simpler: set everything in G2 = β; then the pairing equation
    becomes e(A, β) · e(-α, β) · e(-ic_acc, β) · e(-C, β) = 1, which
    by bilinearity equals e(A - α - ic_acc - C, β). That's 1 iff
    A = α + ic_acc + C in G1.

    So: pick α, C random in G1, ic_acc derived from a random IC[0]
    (and public input count = 0), then A = α + ic_acc + C. Done.
    """
    if public_inputs_count != 0:
        msg = "synthetic test fixture only supports zero public inputs;"
        raise NotImplementedError(msg + " a richer fixture would replicate snarkjs's setup")
    s_alpha = secrets.randbelow(CURVE_ORDER - 1) + 1
    s_ic = secrets.randbelow(CURVE_ORDER - 1) + 1
    s_c = secrets.randbelow(CURVE_ORDER - 1) + 1

    alpha = multiply(G1, s_alpha)
    ic0 = multiply(G1, s_ic)
    c = multiply(G1, s_c)

    # A = α + IC[0] + C   (with public_inputs = [])
    a = add(add(alpha, ic0), c)
    # All G2 elements are β to make the equation factor through bilinearity.
    beta = G2

    vk = VerifyingKey(
        alpha_g1=alpha,
        beta_g2=beta,
        gamma_g2=beta,
        delta_g2=beta,
        ic=(ic0,),
    )
    proof = Proof(a=a, b=beta, c=c)
    return vk, proof, []


def test_verify_accepts_synthetic_valid_proof() -> None:
    vk, proof, public = _build_synthetic_vk_and_proof()
    assert verify(vk, proof, public)


def test_verify_rejects_tampered_a() -> None:
    vk, proof, public = _build_synthetic_vk_and_proof()
    bad = Proof(a=add(proof.a, G1), b=proof.b, c=proof.c)
    assert not verify(vk, bad, public)


def test_verify_rejects_tampered_b() -> None:
    vk, proof, public = _build_synthetic_vk_and_proof()
    bad = Proof(a=proof.a, b=add(proof.b, G2), c=proof.c)
    assert not verify(vk, bad, public)


def test_verify_rejects_tampered_c() -> None:
    vk, proof, public = _build_synthetic_vk_and_proof()
    bad = Proof(a=proof.a, b=proof.b, c=add(proof.c, G1))
    assert not verify(vk, bad, public)


def test_verify_rejects_wrong_public_input_count() -> None:
    vk, proof, _public = _build_synthetic_vk_and_proof()
    # vk has 1 IC entry → expects 0 public inputs.
    assert not verify(vk, proof, [1])
