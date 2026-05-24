# pyright: reportArgumentType=false, reportOptionalCall=false, reportAttributeAccessIssue=false
"""Verkle trees over BLS12-381 KZG polynomial commitments.

Concept taught: a Merkle proof for a leaf in a tree of width w and depth
d carries (w - 1)·d sibling hashes — a 256-ary tree with 1 M leaves
costs 5 KB per proof. A Verkle proof replaces each level's siblings
with ONE KZG polynomial-opening proof (a single elliptic curve point);
a 256-ary Verkle tree of the same depth has constant 48-byte proofs per
level. Ethereum's "Verge" roadmap adopts Verkle trees for the state
tree precisely to amortise proof bandwidth in stateless clients.

KZG in 75 lines
---------------
A KZG commitment to polynomial f(X) is C = [f(s)]₁ for a structured
reference string {[s^i]₁}_{i<=d} produced by a one-time ceremony. The
opening proof for f(z) = y is π = [(f(s) - y) / (s - z)]₁; a verifier
checks e(C - [y]₁, g₂) == e(π, [s]₂ - [z]₂).

This module is verifier-focused: we provide a tiny educational SRS
(small degree, with the *secret* s exposed for demo so the prover can
run without an external ceremony), an honest opening, and a proof-size
calculation vs a comparably-deep Merkle tree.

WARNING — the SRS here uses a known secret s for pedagogy ONLY. A
production deployment requires the toxic waste s to be DESTROYED at
ceremony end; KZG soundness collapses if any party retains s.

References
----------
- Kate, Zaverucha, Goldberg. "Constant-Size Commitments to Polynomials
  and Their Applications" (ASIACRYPT 2010).
- Buterin et al. "Verkle trees" (Ethereum research forum, 2021).
- BLS12-381 curve (Bowe, IETF draft-irtf-cfrg-pairing-friendly-curves).
"""

from __future__ import annotations

import hashlib
import secrets as _secrets
from dataclasses import dataclass
from typing import Final

try:
    from py_ecc.bls12_381 import (
        G1,
        G2,
        add,
        curve_order,
        multiply,
        neg,
        pairing,
    )

    _VERKLE_AVAILABLE = True
except ImportError:  # pragma: no cover - py_ecc is in deps; defensive only
    _VERKLE_AVAILABLE = False
    G1 = G2 = None  # type: ignore[assignment]
    add = multiply = neg = pairing = None  # type: ignore[assignment]
    curve_order = 1


# Educational SRS depth: a polynomial of degree at most _MAX_DEGREE.
# Keep small — every doubling costs a multiply per setup entry.
_MAX_DEGREE: Final[int] = 8


class VerkleError(RuntimeError):
    """Raised on malformed proofs or out-of-range polynomial degrees."""


@dataclass(frozen=True, slots=True)
class KZGSetup:
    """Structured reference string: powers of [s^i]_1 in G1, plus [s]_2 in G2."""

    g1_powers: tuple[object, ...]  # [s^0]_1, [s^1]_1, ..., [s^d]_1
    g2_s: object  # [s]_2
    g2_one: object  # [1]_2 = g2 generator
    _secret_s_for_demo: int  # KEEP PRIVATE — only exposed because no ceremony in tests


@dataclass(frozen=True, slots=True)
class KZGProof:
    """Opening proof for polynomial evaluation f(z) = y."""

    z: int
    y: int
    pi: object  # G1 point


def setup(*, max_degree: int = _MAX_DEGREE) -> KZGSetup:
    """Generate a fresh educational SRS. In production this MUST be a ceremony.

    The toxic waste ``s`` is sampled here and bound into the returned
    setup. A real deployment would run a multi-party computation (Powers
    of Tau) so that no single party knows s, and would discard ``s``
    immediately after generating the SRS.
    """
    if not _VERKLE_AVAILABLE:
        raise VerkleError("py_ecc.bls12_381 unavailable; cannot run KZG")
    s = (int.from_bytes(_secrets.token_bytes(32), "big") % (curve_order - 1)) + 1
    g1_powers = tuple(multiply(G1, pow(s, i, curve_order)) for i in range(max_degree + 1))
    return KZGSetup(
        g1_powers=g1_powers,
        g2_s=multiply(G2, s),
        g2_one=G2,
        _secret_s_for_demo=s,
    )


def _commit_in_g1(setup_: KZGSetup, coeffs: list[int]) -> object:
    """C = Σ coeffs[i] · [s^i]_1 (multi-scalar multiplication in G1)."""
    if len(coeffs) > len(setup_.g1_powers):
        raise VerkleError("polynomial degree exceeds SRS")
    acc: object | None = None
    for c, power in zip(coeffs, setup_.g1_powers, strict=False):
        c_mod = c % curve_order
        if c_mod == 0:
            continue
        term = multiply(power, c_mod)
        acc = term if acc is None else add(acc, term)  # type: ignore[arg-type]
    if acc is None:
        # Zero polynomial → commit to identity. Use [0]·g1 = 0 (point at infinity).
        return multiply(G1, 0)
    return acc


def commit(setup_: KZGSetup, coeffs: list[int]) -> object:
    """Public commitment to f(X) = Σ coeffs[i] X^i, returned as a G1 point."""
    return _commit_in_g1(setup_, coeffs)


def _eval(coeffs: list[int], x: int) -> int:
    """Horner evaluation of f(x) mod curve_order."""
    acc = 0
    for c in reversed(coeffs):
        acc = (acc * x + c) % curve_order
    return acc


def _poly_div_by_linear(coeffs: list[int], z: int) -> list[int]:
    """Divide f(X) - f(z) by (X - z); returns quotient q(X) coefficients.

    Synthetic division in GF(curve_order). The remainder is provably 0
    because (X - z) divides (f(X) - f(z)) exactly.
    """
    n = len(coeffs)
    if n == 0:
        return []
    q: list[int] = [0] * (n - 1)
    carry = 0
    # Walk highest-degree coefficient down to constant.
    for i in range(n - 1, 0, -1):
        carry = (carry * z + coeffs[i]) % curve_order
        q[i - 1] = carry
    return q


def open_proof(setup_: KZGSetup, coeffs: list[int], z: int) -> KZGProof:
    """Construct an opening proof π = [q(s)]_1 with q(X) = (f(X) - f(z)) / (X - z)."""
    y = _eval(coeffs, z)
    shifted = list(coeffs)
    shifted[0] = (shifted[0] - y) % curve_order
    q_coeffs = _poly_div_by_linear(shifted, z)
    pi = _commit_in_g1(setup_, q_coeffs)
    return KZGProof(z=z % curve_order, y=y, pi=pi)


def verify(setup_: KZGSetup, commitment: object, proof: KZGProof) -> bool:
    """Pairing check: e(C - [y]_1, g_2) == e(π, [s]_2 - [z]_2).

    Returns False on any malformed input rather than raising — the
    dashboard's verdict tile relies on a clean True/False signal.
    """
    if not _VERKLE_AVAILABLE:
        return False
    try:
        c_minus_y = add(commitment, neg(multiply(G1, proof.y % curve_order)))
        s_minus_z = add(setup_.g2_s, neg(multiply(setup_.g2_one, proof.z % curve_order)))
        lhs = pairing(setup_.g2_one, c_minus_y)
        rhs = pairing(s_minus_z, proof.pi)
        return bool(lhs == rhs)
    except Exception:
        return False


# ── proof-size economics ──────────────────────────────────────────


def _merkle_proof_bytes(n_leaves: int, hash_bytes: int = 32) -> int:
    """Sibling-hash proof length for a binary Merkle tree."""
    depth = max(1, (n_leaves - 1).bit_length())
    return depth * hash_bytes


def _verkle_proof_bytes(n_leaves: int, width: int = 256, point_bytes: int = 48) -> int:
    """One KZG opening per tree level (48 bytes per G1 compressed point)."""
    if width < 2:
        raise VerkleError("width must be at least 2")
    depth = max(1, _ceil_log(n_leaves, width))
    return depth * point_bytes


def _ceil_log(n: int, base: int) -> int:
    """⌈log_base(n)⌉ for integer n ≥ 1, base ≥ 2."""
    depth, prod = 0, 1
    while prod < n:
        prod *= base
        depth += 1
    return depth


def demo(*, n_leaves: int = 1_000_000) -> dict[str, object]:
    """End-to-end KZG opening on a small polynomial + proof-size comparison."""
    if not _VERKLE_AVAILABLE:
        return {
            "available": False,
            "reason": "py_ecc.bls12_381 not installed",
            "merkle_proof_bytes": _merkle_proof_bytes(n_leaves),
            "verkle_proof_bytes": _verkle_proof_bytes(n_leaves),
            "compression_ratio": round(
                _merkle_proof_bytes(n_leaves) / _verkle_proof_bytes(n_leaves), 2
            ),
        }
    setup_ = setup(max_degree=4)
    coeffs = [3, 1, 4, 1, 5]  # f(X) = 3 + X + 4X^2 + X^3 + 5X^4
    z = int.from_bytes(hashlib.sha256(b"penumbra-verkle-eval-point").digest(), "big") % 257
    commitment = commit(setup_, coeffs)
    proof = open_proof(setup_, coeffs, z)
    honest_ok = verify(setup_, commitment, proof)
    tampered = KZGProof(z=proof.z, y=(proof.y + 1) % curve_order, pi=proof.pi)
    tampered_ok = verify(setup_, commitment, tampered)

    merkle_bytes = _merkle_proof_bytes(n_leaves)
    verkle_bytes = _verkle_proof_bytes(n_leaves)
    return {
        "available": True,
        "algorithm": "KZG on BLS12-381 (Verkle proof-of-concept)",
        "n_leaves": int(n_leaves),
        "merkle_proof_bytes": merkle_bytes,
        "verkle_proof_bytes": verkle_bytes,
        "compression_ratio": round(merkle_bytes / max(1, verkle_bytes), 2),
        "evaluation_point_z": int(z),
        "evaluation_y": int(proof.y),
        "honest_verifies": bool(honest_ok),
        "tampered_y_verifies": bool(tampered_ok),
        "notes": (
            "Educational SRS — the toxic waste s is retained for demo "
            "purposes. Production deployments run a Powers-of-Tau "
            "ceremony and destroy s."
        ),
    }
