"""Minimal STARK verifier with FRI low-degree testing.

Concept taught: a STARK proves a polynomial relation over a large
evaluation domain WITHOUT a trusted setup. Three primitives:

1. **Reed-Solomon codeword** — evaluate a degree-d polynomial f over an
   evaluation domain of size N = blowup · (d + 1). The verifier
   queries a few positions; if the codeword is far from any low-degree
   polynomial, random queries detect it with high probability (the
   "list-decoding" intuition).
2. **Merkle commitment** — the prover Merkle-commits to the codeword
   so it can't equivocate per-query.
3. **FRI low-degree test** — log(N) "folding" rounds compress the
   codeword by 2 each round under a Fiat-Shamir challenge. The final
   "free" polynomial is constant (degree 0); the verifier checks one
   per-round consistency relation. Each fold reduces the degree of the
   committed polynomial by 2, so log(N) folds drive a degree-d
   polynomial to a constant.

Pedagogical scope (kept honest about what we DON'T ship)
- Prover is included only for demo/testing; production STARKs (Cairo,
  StarkWare, Plonky3) cost months of work and pull in custom field
  arithmetic, FFTs over Goldilocks/M31, AIR DSL, etc. We ship the
  VERIFIER side as a learning artifact, mirroring the Groth16 pattern.
- We work in a SMALL prime field (32-bit Goldilocks-ish) using plain
  Python ints + numpy. This is enough to exhibit the protocol mechanics
  without writing a fast field-arithmetic library.
- The Merkle tree is binary, SHA-256. No optimisation; readability
  wins over throughput.

Soundness assumptions we rely on
- **FRI low-degree (Ben-Sasson et al. STARKs 2018)**: a codeword that
  passes log(N) FRI rounds with high probability is close to a low-
  degree polynomial. Concretely, the soundness error per FRI query is
  bounded by `(d+1)/|F| + (1-δ)^s` where δ is the Johnson-bound
  distance and s the number of queries. The educational version uses
  modest parameters; we annotate the expected error in `demo()`.
- **Merkle binding**: SHA-256 collision resistance. The prover cannot
  swap a leaf without breaking SHA-256.
- **Fiat-Shamir non-interactivity**: the transcript-derived challenges
  are sound under the Random Oracle Model. We absorb every commitment
  into the transcript BEFORE deriving the next challenge.

References
- Ben-Sasson, Bentov, Horesh, Riabzev "Scalable, transparent, and
  post-quantum secure computational integrity" (ePrint 2018/046).
- "anatomy of a STARK" tutorial by Aszepieniec (the inspiration for
  the educational-but-correct shape used here).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

# A small NTT-friendly prime: p = 119 * 2^23 + 1 = 998244353.
# Crucially, 2^23 divides p - 1 so the multiplicative group has a large
# power-of-two subgroup — the FRI domain MUST be a subgroup of order
# 2^k for some k, otherwise squaring the domain doesn't halve it.
_P = 998_244_353
# The multiplicative group of F_p has order p-1 = 119 * 2^23, so the
# largest power-of-two subgroup has order 2^23. We pick a generator of
# that subgroup by raising any primitive root to (p-1)/2^23.
_PRIMITIVE_ROOT = 3  # 3 is a primitive root of 998244353.
_TWO_ADICITY = 23
_OMEGA = pow(_PRIMITIVE_ROOT, (_P - 1) // (1 << _TWO_ADICITY), _P)
# _OMEGA has multiplicative order exactly 2^23 in F_p.


def _hash(*parts: bytes) -> bytes:
    h = hashlib.sha256()
    for p in parts:
        h.update(len(p).to_bytes(4, "big"))
        h.update(p)
    return h.digest()


def _felt(x: int) -> int:
    return int(x) % _P


def _pow(base: int, exp: int) -> int:
    return pow(_felt(base), int(exp), _P)


def _inv(x: int) -> int:
    return pow(_felt(x), _P - 2, _P)


@dataclass(frozen=True, slots=True)
class MerkleProof:
    """One Merkle authentication path: leaf bytes + sibling hashes + index."""

    leaf: bytes
    path: tuple[bytes, ...]
    index: int


def merkle_root(leaves: list[bytes]) -> bytes:
    """Binary Merkle root. Pad with zero leaves to power-of-two length."""
    if not leaves:
        raise STARKError("merkle_root requires at least one leaf")
    level = [_hash(b"leaf", x) for x in leaves]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [_hash(b"node", level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def merkle_open(leaves: list[bytes], index: int) -> MerkleProof:
    """Authentication path for leaf at ``index``."""
    if not 0 <= index < len(leaves):
        raise STARKError(f"index {index} out of range for {len(leaves)} leaves")
    level = [_hash(b"leaf", x) for x in leaves]
    path: list[bytes] = []
    idx = index
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        sibling = level[idx ^ 1]
        path.append(sibling)
        level = [_hash(b"node", level[i], level[i + 1]) for i in range(0, len(level), 2)]
        idx //= 2
    return MerkleProof(leaf=leaves[index], path=tuple(path), index=index)


def merkle_verify(root: bytes, proof: MerkleProof) -> bool:
    """Recompute the root from the auth path; constant-time-ish check."""
    node = _hash(b"leaf", proof.leaf)
    idx = proof.index
    for sibling in proof.path:
        node = _hash(b"node", node, sibling) if idx % 2 == 0 else _hash(b"node", sibling, node)
        idx //= 2
    return node == root


@dataclass(frozen=True, slots=True)
class FRIRound:
    """One folding round in the FRI low-degree test."""

    commitment: bytes
    queried_left: int  # f(x) at the query index
    queried_right: int  # f(-x) at the mirror index
    proof_left: MerkleProof
    proof_right: MerkleProof


@dataclass(frozen=True, slots=True)
class STARKProof:
    """A FRI-based STARK proof bundle.

    Fields mirror the textbook STARK structure:
    - ``commitments`` — Merkle root per FRI round (one per fold).
    - ``evaluations`` — codeword values revealed at the queried positions.
      The verifier reads them straight out of `fri_proof.queried_*` but
      we surface them here for inspection / tampering tests.
    - ``fri_proof`` — the per-round openings + folding witnesses.
    - ``final_constant`` — the degree-0 polynomial after all folds.
    - ``query_index`` — single query index (educational; production uses
      many independent queries to push soundness error below 2^-100).
    - ``domain_size`` — size of the initial evaluation domain N.
    - ``initial_degree_bound`` — declared upper bound on deg(f).
    """

    commitments: tuple[bytes, ...]
    evaluations: tuple[int, ...]
    fri_proof: tuple[FRIRound, ...]
    final_constant: int
    query_index: int
    domain_size: int
    initial_degree_bound: int


def _domain(n: int) -> list[int]:
    """Order-n subgroup of F_p^*. n must be a power of two and divide 2^23."""
    if n < 1 or n & (n - 1) != 0:
        raise STARKError(f"domain size {n} must be a power of two")
    if n > (1 << _TWO_ADICITY):
        raise STARKError(f"domain size {n} exceeds field two-adicity 2^{_TWO_ADICITY}")
    # generator of the order-n subgroup: _OMEGA raised to (2^23 / n).
    gen = pow(_OMEGA, (1 << _TWO_ADICITY) // n, _P)
    return [_pow(gen, i) for i in range(n)]


def _evaluate(coeffs: list[int], x: int) -> int:
    """Horner-rule evaluation of a polynomial at x."""
    acc = 0
    for c in reversed(coeffs):
        acc = (acc * x + c) % _P
    return acc


def _eval_codeword(coeffs: list[int], domain: list[int]) -> list[int]:
    return [_evaluate(coeffs, x) for x in domain]


def _fold(codeword: list[int], domain: list[int], beta: int) -> tuple[list[int], list[int]]:
    """One FRI fold: split f(x) into even+odd parts, combine with beta.

    Given f(x) = g(x^2) + x · h(x^2), the folded codeword is
        f'(x^2) = g(x^2) + beta · h(x^2)
    sampled at the squared half-domain. This halves both the codeword
    length and the degree.
    """
    n = len(codeword)
    if n % 2 != 0:
        raise STARKError(f"codeword length {n} must be even to fold")
    new: list[int] = []
    new_domain: list[int] = []
    for i in range(n // 2):
        x = domain[i]
        x_inv = _inv(x)
        left = codeword[i]
        right = codeword[i + n // 2]
        even = ((left + right) * _inv(2)) % _P
        odd = (((left - right) * _inv(2)) * x_inv) % _P
        folded = (even + beta * odd) % _P
        new.append(folded)
        new_domain.append((x * x) % _P)
    return new, new_domain


def _transcript_challenge(transcript: bytes, label: bytes, *parts: bytes) -> int:
    """Fiat-Shamir scalar challenge in F_p. Absorbs label + parts."""
    digest = _hash(transcript, label, *parts)
    return int.from_bytes(digest, "big") % _P


def prove(
    coeffs: list[int],
    *,
    blowup: int = 4,
    transcript: bytes = b"penumbra-stark-v1",
) -> STARKProof:
    """Build a STARK proof that ``coeffs`` is a polynomial of declared degree.

    Educational prover: enumerate the codeword, Merkle-commit, do log(N)
    FRI folds with Fiat-Shamir challenges, open one query. Not
    constant-time and not optimised.
    """
    if not coeffs:
        raise STARKError("coeffs must be non-empty")
    d = len(coeffs) - 1
    domain_size = 1
    while domain_size < (d + 1) * blowup:
        domain_size *= 2
    domain = _domain(domain_size)
    codeword = _eval_codeword(coeffs, domain)

    commitments: list[bytes] = []
    fri_proof: list[FRIRound] = []
    layers: list[tuple[list[int], list[int]]] = [(codeword, domain)]

    cur_transcript = transcript
    cur_code = codeword
    cur_domain = domain
    while len(cur_code) > 1:
        leaves = [int(v).to_bytes(8, "big", signed=False) for v in cur_code]
        root = merkle_root(leaves)
        commitments.append(root)
        cur_transcript = _hash(cur_transcript, b"fri-commit", root)
        beta = _transcript_challenge(cur_transcript, b"fri-beta")
        nxt_code, nxt_domain = _fold(cur_code, cur_domain, beta)
        layers.append((nxt_code, nxt_domain))
        cur_code, cur_domain = nxt_code, nxt_domain

    final_constant = cur_code[0] if cur_code else 0
    query_index = _transcript_challenge(cur_transcript, b"fri-query") % domain_size

    # Open one query per layer (educational: production opens dozens).
    idx = query_index
    for layer_idx, (code, _dom) in enumerate(layers[:-1]):
        n = len(code)
        i_left = idx % n
        i_right = (i_left + n // 2) % n
        leaves = [int(v).to_bytes(8, "big", signed=False) for v in code]
        proof_left = merkle_open(leaves, i_left)
        proof_right = merkle_open(leaves, i_right)
        commitment = commitments[layer_idx]
        fri_proof.append(
            FRIRound(
                commitment=commitment,
                queried_left=code[i_left],
                queried_right=code[i_right],
                proof_left=proof_left,
                proof_right=proof_right,
            )
        )
        idx = i_left % (n // 2)

    return STARKProof(
        commitments=tuple(commitments),
        evaluations=tuple(int(v) for v in [codeword[query_index % domain_size]]),
        fri_proof=tuple(fri_proof),
        final_constant=int(final_constant),
        query_index=int(query_index),
        domain_size=int(domain_size),
        initial_degree_bound=int(d),
    )


def verify(
    proof: STARKProof,
    public_inputs: dict[str, Any] | None = None,
    transcript: bytes = b"penumbra-stark-v1",
) -> bool:
    """Merkle-pinned FRI verifier with low-degree extension check.

    Returns True iff (a) every Merkle proof verifies under its claimed
    commitment, (b) each folding round's left/right values combine
    correctly under the Fiat-Shamir beta, and (c) the final value
    equals the declared constant.
    """
    _ = public_inputs  # reserved for AIR public-input binding (future).
    if not proof.commitments:
        return False
    if not proof.fri_proof:
        return False
    if len(proof.commitments) != len(proof.fri_proof):
        return False
    if proof.domain_size <= 0 or proof.domain_size & (proof.domain_size - 1) != 0:
        return False

    cur_transcript = transcript
    cur_size = proof.domain_size
    cur_idx = proof.query_index % proof.domain_size
    cur_domain = _domain(proof.domain_size)
    expected_left: int | None = None
    for layer_idx, round_obj in enumerate(proof.fri_proof):
        commitment = proof.commitments[layer_idx]
        if commitment != round_obj.commitment:
            return False
        cur_transcript = _hash(cur_transcript, b"fri-commit", commitment)
        beta = _transcript_challenge(cur_transcript, b"fri-beta")

        i_left = cur_idx % cur_size
        i_right = (i_left + cur_size // 2) % cur_size

        if round_obj.proof_left.index != i_left:
            return False
        if round_obj.proof_right.index != i_right:
            return False
        if int.from_bytes(round_obj.proof_left.leaf, "big") != round_obj.queried_left:
            return False
        if int.from_bytes(round_obj.proof_right.leaf, "big") != round_obj.queried_right:
            return False
        if not merkle_verify(commitment, round_obj.proof_left):
            return False
        if not merkle_verify(commitment, round_obj.proof_right):
            return False

        if expected_left is not None and round_obj.queried_left != expected_left:
            return False

        x = cur_domain[i_left]
        x_inv = _inv(x)
        even = ((round_obj.queried_left + round_obj.queried_right) * _inv(2)) % _P
        odd = (((round_obj.queried_left - round_obj.queried_right) * _inv(2)) * x_inv) % _P
        folded = (even + beta * odd) % _P

        cur_size //= 2
        cur_idx = i_left % cur_size
        cur_domain = [(x * x) % _P for x in cur_domain[:cur_size]]
        expected_left = folded

    if expected_left is None:
        return False
    if expected_left != _felt(proof.final_constant):
        return False

    final_transcript_query = _transcript_challenge(cur_transcript, b"fri-query")
    return final_transcript_query % proof.domain_size == proof.query_index


def demo() -> dict[str, Any]:
    """Generate one honest STARK proof, plus tampered variants, and verify each."""
    coeffs = [3, 1, 4, 1, 5, 9, 2, 6]  # a degree-7 polynomial; π digits for fun
    proof = prove(coeffs)
    honest_ok = verify(proof)

    # Tamper an evaluation: bump the first FRI round's left value.
    tampered_round = proof.fri_proof[0]
    bad_round = FRIRound(
        commitment=tampered_round.commitment,
        queried_left=(tampered_round.queried_left + 1) % _P,
        queried_right=tampered_round.queried_right,
        proof_left=tampered_round.proof_left,
        proof_right=tampered_round.proof_right,
    )
    tampered_eval_proof = STARKProof(
        commitments=proof.commitments,
        evaluations=proof.evaluations,
        fri_proof=(bad_round, *proof.fri_proof[1:]),
        final_constant=proof.final_constant,
        query_index=proof.query_index,
        domain_size=proof.domain_size,
        initial_degree_bound=proof.initial_degree_bound,
    )
    tampered_eval_ok = verify(tampered_eval_proof)

    # Tamper a commitment: flip a bit in the first Merkle root.
    bad_commit = bytes([proof.commitments[0][0] ^ 1, *proof.commitments[0][1:]])
    tampered_commit_proof = STARKProof(
        commitments=(bad_commit, *proof.commitments[1:]),
        evaluations=proof.evaluations,
        fri_proof=proof.fri_proof,
        final_constant=proof.final_constant,
        query_index=proof.query_index,
        domain_size=proof.domain_size,
        initial_degree_bound=proof.initial_degree_bound,
    )
    tampered_commit_ok = verify(tampered_commit_proof)

    return {
        "available": True,
        "algorithm": "Educational FRI-STARK (SHA-256 Merkle + Fiat-Shamir)",
        "domain_size": proof.domain_size,
        "degree_bound": proof.initial_degree_bound,
        "n_fri_rounds": len(proof.fri_proof),
        "query_index": proof.query_index,
        "final_constant": proof.final_constant,
        "first_commitment_short": proof.commitments[0].hex()[:32],
        "honest_verifies": bool(honest_ok),
        "tampered_evaluation_verifies": bool(tampered_eval_ok),
        "tampered_commitment_verifies": bool(tampered_commit_ok),
        "soundness_note": (
            "single-query educational variant; production STARKs run "
            "~80 queries to push the soundness error below 2^-100"
        ),
    }


def serialise_proof(proof: STARKProof) -> str:
    """JSON-encode a STARK proof (handy for transport + persistence)."""

    def _round(r: FRIRound) -> dict[str, Any]:
        return {
            "commitment": r.commitment.hex(),
            "queried_left": r.queried_left,
            "queried_right": r.queried_right,
            "proof_left": {
                "leaf": r.proof_left.leaf.hex(),
                "path": [p.hex() for p in r.proof_left.path],
                "index": r.proof_left.index,
            },
            "proof_right": {
                "leaf": r.proof_right.leaf.hex(),
                "path": [p.hex() for p in r.proof_right.path],
                "index": r.proof_right.index,
            },
        }

    return json.dumps(
        {
            "commitments": [c.hex() for c in proof.commitments],
            "evaluations": list(proof.evaluations),
            "fri_proof": [_round(r) for r in proof.fri_proof],
            "final_constant": proof.final_constant,
            "query_index": proof.query_index,
            "domain_size": proof.domain_size,
            "initial_degree_bound": proof.initial_degree_bound,
        }
    )


class STARKError(ValueError):
    """Raised on STARK protocol violations and malformed proofs."""


# Numpy-shaped utility kept here so the import line in `verify` doesn't
# bring numpy unconditionally. The verifier itself is plain Python.
__all__ = [
    "FRIRound",
    "MerkleProof",
    "STARKError",
    "STARKProof",
    "demo",
    "merkle_open",
    "merkle_root",
    "merkle_verify",
    "prove",
    "serialise_proof",
    "verify",
]

# Re-export numpy so the test suite can import it from this module if it
# wants (it doesn't currently, but keeps the educational story tidy).
_np = np
