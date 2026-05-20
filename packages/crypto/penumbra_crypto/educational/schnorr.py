"""Schnorr Σ-protocol + Fiat-Shamir non-interactive ZK proof of knowledge.

Concept taught: a prover convinces a verifier that they know x such that
y = g^x mod p, **without revealing x**. Three moves:

    Commit:    r ←R Z_q;  t = g^r        (prover broadcasts t)
    Challenge: c ←R Z_q                  (verifier broadcasts c)
    Response:  s = r + c·x  mod q        (prover broadcasts s)

Verify: accept iff g^s ≡ t · y^c (mod p).

This is sound (no prover can answer for both c and c' without knowing x;
two valid responses for distinct challenges extract x) and honest-verifier
zero-knowledge (the simulator picks s, c ←R, sets t = g^s · y^{-c};
the transcript is indistinguishable from a real one).

Fiat-Shamir turns the interactive protocol non-interactive by deriving
the challenge from a hash of (g, y, t) plus a context string. The cost
is the *random oracle* assumption on the hash.

Penumbra uses this pattern as the building block for:
- Proof-of-possession for BLS validator keys (rogue-key defence)
- Proof of legal-action knowledge in the attacker console's forgery
  demo (so the learner can see exactly *why* replaying transcripts
  doesn't help)

References
- Schnorr, "Efficient signature generation by smart cards" (J. Crypt. 1991).
- Fiat, Shamir, "How to prove yourself" (CRYPTO 1986).

Pedagogical caveats
- The challenge MUST be derived from a transcript that includes both g, y
  AND t. Skipping t would let an attacker pick (c, s) first and forge t.
  This is the most common Fiat-Shamir bug (Bernhard et al., 2012).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from penumbra_crypto.educational.pedersen import group_params

_P, _Q, _G, _H = group_params()
# We use the same group as Pedersen so educational composition demos work.
# y is the public statement, x the secret witness; both live in this group.


@dataclass(frozen=True, slots=True)
class Statement:
    """Public input: y = g^x mod p. Verifier sees y, prover knows x."""

    y: int


@dataclass(frozen=True, slots=True)
class Proof:
    """Non-interactive proof transcript."""

    t: int  # commitment
    s: int  # response
    c: int  # Fiat-Shamir challenge (recomputable but cached)


def keygen() -> tuple[int, Statement]:
    """Sample a witness x ∈ Z_q and publish y = g^x. Returns (x, statement)."""
    x = secrets.randbelow(_Q - 1) + 1  # avoid zero
    return x, Statement(y=pow(_G, x, _P))


def prove(witness: int, statement: Statement, *, context: bytes = b"") -> Proof:
    """Produce a Fiat-Shamir Schnorr proof of knowledge of `witness`.

    `context` is a domain-separation string included in the challenge
    transcript so that proofs are bound to where they're used.
    """
    if pow(_G, witness, _P) != statement.y:
        raise ValueError("witness does not match statement (g^x != y)")
    r = secrets.randbelow(_Q - 1) + 1  # avoid zero
    t = pow(_G, r, _P)
    c = _challenge(statement.y, t, context)
    s = (r + c * witness) % _Q
    return Proof(t=t, s=s, c=c)


def verify(statement: Statement, proof: Proof, *, context: bytes = b"") -> bool:
    """Check g^s ≡ t · y^c (mod p) and that c was correctly derived."""
    # Verifier independently recomputes the challenge — refusing to
    # accept a forged c that was never in the transcript. This is what
    # closes the Bernhard et al. (2012) class of Fiat-Shamir bugs.
    expected_c = _challenge(statement.y, proof.t, context)
    if proof.c != expected_c:
        return False
    if not (0 <= proof.s < _Q):
        return False
    if not (0 < proof.t < _P):
        return False
    lhs = pow(_G, proof.s, _P)
    rhs = (proof.t * pow(statement.y, proof.c, _P)) % _P
    return lhs == rhs


def _challenge(y: int, t: int, context: bytes) -> int:
    """Fiat-Shamir: c = H(domain | y | t | context) mod q.

    Domain tag prevents cross-protocol replay; including `t` is what
    keeps the proof non-malleable (see Bernhard, Pereira, Warinschi,
    "How not to prove yourself", 2012).
    """
    h = hashlib.sha256()
    h.update(b"penumbra-schnorr-v1")
    h.update(y.to_bytes(256, "big"))
    h.update(t.to_bytes(256, "big"))
    h.update(context)
    return int.from_bytes(h.digest(), "big") % _Q
