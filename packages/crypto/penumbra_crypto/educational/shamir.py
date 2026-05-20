"""Shamir secret sharing — pedagogical implementation.

Concept taught: a degree-(t-1) polynomial over a prime field is uniquely
determined by *any* t points but is information-theoretically unknown
given fewer than t. We hide a secret `s` as `P(0) = s` of a random
polynomial of degree t-1, hand out `n` distinct evaluations `(x_i, P(x_i))`,
and any t shareholders can reconstruct `s` by Lagrange interpolation.

Security
--------
- Information-theoretic. No assumption beyond a uniform polynomial.
- Fewer than t shares reveal **nothing** about s (perfect secrecy).

References
- Shamir, "How to share a secret" (Comm. ACM 1979).

Pedagogical caveats
- Uses Python ``secrets`` for randomness (cryptographic).
- The prime is the secp256k1 group order — fits all 256-bit secrets
  and is large enough that polynomial arithmetic is exact in Python's
  arbitrary-precision integers.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Final

# secp256k1 group order n; any prime > 2**256 would work — we just need
# headroom over 256-bit secrets.
_PRIME: Final[int] = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


@dataclass(frozen=True, slots=True)
class Share:
    """One Shamir share: an evaluation point on the secret polynomial."""

    x: int
    y: int


def _random_field_element() -> int:
    return secrets.randbelow(_PRIME)


def _eval_polynomial(coeffs: list[int], x: int) -> int:
    """Horner-rule evaluation in GF(p)."""
    acc = 0
    for c in reversed(coeffs):
        acc = (acc * x + c) % _PRIME
    return acc


def split(secret: int, *, n: int, t: int) -> list[Share]:
    """Split `secret` into `n` shares, any `t` of which can reconstruct it.

    Generates random coefficients a_1, …, a_{t-1} ∈ GF(p) and forms
    P(x) = secret + a_1·x + a_2·x² + … + a_{t-1}·x^{t-1}. Each
    shareholder i ∈ {1..n} receives (i, P(i)).
    """
    if not 1 <= t <= n:
        raise ValueError(f"need 1 <= t <= n; got t={t}, n={n}")
    if not 0 <= secret < _PRIME:
        raise ValueError("secret must be in the field [0, prime)")
    coeffs = [secret] + [_random_field_element() for _ in range(t - 1)]
    return [Share(x=i, y=_eval_polynomial(coeffs, i)) for i in range(1, n + 1)]


def reconstruct(shares: list[Share]) -> int:
    """Reconstruct the secret by Lagrange interpolation at x=0.

    Given t distinct shares (x_1, y_1) … (x_t, y_t),

        secret = Σ_i y_i · Π_{j≠i} (-x_j) / (x_i - x_j)   (mod p)

    Division in GF(p) is multiplication by the modular inverse (Fermat's
    little theorem: a^{-1} = a^{p-2} mod p).
    """
    if len({s.x for s in shares}) != len(shares):
        raise ValueError("duplicate x-coordinates in shares")
    if len(shares) < 1:
        raise ValueError("need at least one share")

    total = 0
    for i, share_i in enumerate(shares):
        num, den = 1, 1
        for j, share_j in enumerate(shares):
            if i == j:
                continue
            num = (num * (-share_j.x)) % _PRIME
            den = (den * (share_i.x - share_j.x)) % _PRIME
        lagrange_i = (num * pow(den, _PRIME - 2, _PRIME)) % _PRIME
        total = (total + share_i.y * lagrange_i) % _PRIME
    return total


def field_modulus() -> int:
    """Expose the prime modulus so callers can stay within range."""
    return _PRIME
