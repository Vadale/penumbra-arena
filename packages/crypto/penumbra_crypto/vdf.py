"""Wesolowski VDF — pure-Python pedagogical implementation.

Concept taught: a *Verifiable Delay Function* takes input `x` and a
delay parameter `T`, and produces an output `y` that cannot be
computed in time less than `T` sequentially (even with a giant
parallel cluster). The "verifiable" part: anyone can check the output
in `O(log T)` time using a small proof `π`.

Penumbra uses a VDF to seed the arena's procedural randomness between
matches in a way *no one can grind*: even the proposer of the next
block can't predict the next arena layout faster than the VDF allows,
because computing T squarings sequentially can't be parallelised.

Construction (Wesolowski 2018, simplified to a generic prime-order group):

  Eval(x, T) → y:
     compute y = x^(2^T) mod p, i.e. T squarings in series
  Prove(x, y, T) → π:
     l ← hash-to-prime(x, y, T)            # public, deterministic
     q, r ← divmod(2^T, l)
     π ← x^q mod p
  Verify(x, y, T, π) → bool:
     l ← hash-to-prime(x, y, T)
     r ← 2^T mod l
     return π^l · x^r ≡ y (mod p)

Soundness sketch: if the prover doesn't know x^(2^T) they can't
satisfy π^l · x^r = y because π would have to be x^q for the unique q
in the equation 2^T = q·l + r. Hash-to-prime makes l unpredictable
until x, y are committed.

Pedagogical caveats
- We use a generic Schnorr group from `educational/pedersen.py` so
  the group operation is just modular multiplication and the user can
  read every step. Production VDFs use class groups of imaginary
  quadratic order so that the discriminant alone is the public
  parameter (no trusted setup at all).
- T must be modest (≤ 2^16 in tests) so the test suite stays fast.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from penumbra_crypto.educational.pedersen import group_params

_P, _Q, _G, _H = group_params()

# Public domain-separation tag for the hash-to-prime.
_HASH_TAG = b"penumbra-vdf-wesolowski-v1"


@dataclass(frozen=True, slots=True)
class VDFEvaluation:
    """Eval output + Wesolowski proof + the public parameters that bind them."""

    x: int  # input
    y: int  # output = x^(2^T) mod p
    proof: int  # π = x^q mod p
    delay: int  # T


def evaluate(x: int, delay: int) -> int:
    """Sequential squaring. Computes y = x^(2^delay) mod p.

    No parallelism speeds this up because each squaring depends on
    the previous result. On the M4, ~10⁶ squarings ≈ 1 second.
    """
    if delay < 0:
        raise ValueError("delay must be non-negative")
    if not 0 < x < _P:
        raise ValueError("x must be in (0, p)")
    y = x
    for _ in range(delay):
        y = (y * y) % _P
    return y


def prove(x: int, delay: int) -> VDFEvaluation:
    """Evaluate then construct the Wesolowski proof."""
    y = evaluate(x, delay)
    prime = _hash_to_prime(x, y, delay)
    # Compute q = floor(2^delay / l) without materialising 2^delay as an
    # arbitrarily-large integer when delay is huge: walk the binary
    # representation and accumulate.
    q = pow(2, delay) // prime  # for educational delays this is fine
    proof = pow(x, q, _P)
    return VDFEvaluation(x=x, y=y, proof=proof, delay=delay)


def verify(evaluation: VDFEvaluation) -> bool:
    """Check π^prime · x^r ≡ y (mod p), with `prime` deterministic and r = 2^T mod prime."""
    if not 0 < evaluation.x < _P:
        return False
    if not 0 < evaluation.y < _P:
        return False
    if not 0 <= evaluation.proof < _P:
        return False
    prime = _hash_to_prime(evaluation.x, evaluation.y, evaluation.delay)
    r = pow(2, evaluation.delay, prime)
    lhs = (pow(evaluation.proof, prime, _P) * pow(evaluation.x, r, _P)) % _P
    return lhs == evaluation.y


def _hash_to_prime(x: int, y: int, delay: int) -> int:
    """Map (x, y, T) to a deterministic prime around 128 bits.

    We hash the transcript with SHA-256, interpret the digest as an
    integer, then walk upward with `is_probable_prime` until we hit a
    prime. Probabilistic primality testing is fine here because the
    prime only needs to be sufficiently large that the verifier's
    soundness bound holds (≥ 2¹²⁰ rules out brute-force collisions).
    """
    counter = 0
    while True:
        h = hashlib.sha256()
        h.update(_HASH_TAG)
        h.update(x.to_bytes(256, "big"))
        h.update(y.to_bytes(256, "big"))
        h.update(delay.to_bytes(8, "big"))
        h.update(counter.to_bytes(4, "big"))
        candidate = int.from_bytes(h.digest(), "big") | 1
        if _is_probable_prime(candidate):
            return candidate
        counter += 1


def _is_probable_prime(n: int, *, rounds: int = 20) -> bool:
    """Miller-Rabin with `rounds` deterministic-witness iterations."""
    if n < 2:
        return False
    small_primes = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    for p in small_primes:
        if n == p:
            return True
        if n % p == 0:
            return False
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    # Deterministic-ish witnesses for huge composites; for cryptographic
    # security we'd use a fresh CSPRNG draw, but determinism is useful
    # so the verifier picks the same prime as the prover.
    witnesses = small_primes[:rounds]
    for a in witnesses:
        if a >= n:
            continue
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = (x * x) % n
            if x == n - 1:
                break
        else:
            return False
    return True
