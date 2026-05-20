"""Beaver multiplication triples — pedagogical SMPC primitive.

Concept taught: secret sharing supports linear operations *for free* (add
shares pointwise to add the secrets) but multiplication of two shared
secrets is non-trivial: a naive pointwise product gives shares of a
polynomial of doubled degree, requiring a degree-reduction round.

Beaver's idea (1991): pre-compute, offline, batches of correlated
randomness — triples (a, b, c) with c = a·b in GF(p) — each party
holding additive shares of all three. Then online, multiplying secret-
shared X and Y is a single broadcast of two field elements per party:

    d = X - a   (revealed; safe because a is uniform)
    e = Y - b   (revealed; safe because b is uniform)
    Z = X·Y = (d + a)(e + b) = d·e + d·b + e·a + a·b

Reconstruction: party 0 contributes the constant d·e; every party
contributes shares of d·b + e·a + c locally — *no* multiplication of
two secret values online. The trick is that a, b, c were already
multiplied **offline** when the triple was generated.

References
- Beaver, "Efficient multiparty protocols using circuit randomization"
  (CRYPTO 1991), §2.

Pedagogical caveats
- We use *additive* secret sharing here (Shamir is the alternative);
  additive sharing is simpler to inspect.
- Single-shot triple generation by a trusted dealer in this file. A
  real SMPC stack generates triples via a separate offline protocol
  (e.g. OT-based or HE-based).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from penumbra_crypto.educational.shamir import field_modulus

_PRIME = field_modulus()


@dataclass(frozen=True, slots=True)
class Triple:
    """One Beaver triple shared additively across n parties.

    `a_shares[i] + b_shares[i] + c_shares[i] sums (mod p) reconstruct
    a, b, c respectively, and c = a*b (mod p).
    """

    a_shares: tuple[int, ...]
    b_shares: tuple[int, ...]
    c_shares: tuple[int, ...]

    @property
    def n_parties(self) -> int:
        return len(self.a_shares)


def _additive_shares(value: int, n: int) -> tuple[int, ...]:
    """Split `value` into n additive shares summing to `value` (mod p)."""
    head = tuple(secrets.randbelow(_PRIME) for _ in range(n - 1))
    tail = (value - sum(head)) % _PRIME
    return (*head, tail)


def generate_triple(n_parties: int) -> Triple:
    """Trusted-dealer Beaver triple for `n_parties` participants.

    The dealer samples a, b uniformly, computes c = a*b mod p, and
    additively-shares each across the parties. In a real protocol the
    dealer would be replaced by an offline two-party computation that
    no single party can subvert.
    """
    if n_parties < 2:
        raise ValueError("Beaver triples need at least 2 parties")
    a = secrets.randbelow(_PRIME)
    b = secrets.randbelow(_PRIME)
    c = (a * b) % _PRIME
    return Triple(
        a_shares=_additive_shares(a, n_parties),
        b_shares=_additive_shares(b, n_parties),
        c_shares=_additive_shares(c, n_parties),
    )


def beaver_multiply(
    x_shares: tuple[int, ...],
    y_shares: tuple[int, ...],
    triple: Triple,
) -> tuple[int, ...]:
    """Compute additive shares of x·y, using Beaver's identity.

    Each party local steps:
      1. Compute its share of d = x - a and of e = y - b.
      2. Open d, e (broadcast).
      3. Locally form its z share via
            z_i = c_i + d * b_i + e * a_i + (d * e if i == 0 else 0)
    Sums of z_i over parties give x·y mod p.
    """
    n = triple.n_parties
    if len(x_shares) != n or len(y_shares) != n:
        raise ValueError("x_shares and y_shares must match the triple width")

    # Step 1+2: each party computes its own d_i, e_i, then "broadcasts" them.
    # In a real protocol this is the only network round.
    d_shares = [(x_shares[i] - triple.a_shares[i]) % _PRIME for i in range(n)]
    e_shares = [(y_shares[i] - triple.b_shares[i]) % _PRIME for i in range(n)]
    d = sum(d_shares) % _PRIME
    e = sum(e_shares) % _PRIME

    # Step 3: local share of z.
    z_shares: list[int] = []
    for i in range(n):
        local = (triple.c_shares[i] + d * triple.b_shares[i] + e * triple.a_shares[i]) % _PRIME
        if i == 0:
            local = (local + d * e) % _PRIME
        z_shares.append(local)
    return tuple(z_shares)


def reconstruct_sum(shares: tuple[int, ...]) -> int:
    """Reconstruct a secret from additive shares (mod p)."""
    return sum(shares) % _PRIME
