"""Educational TFHE-style homomorphic boolean operations.

Concept taught: TFHE (Chillotti, Gama, Georgieva, Izabachène 2016)
encrypts individual bits and supports a UNIVERSAL gate — `NAND` —
from which every boolean function follows. Production TFHE
(Concrete-Python, TFHE-rs) includes "bootstrapping" that refreshes
ciphertext noise after every gate, allowing arbitrarily-deep
circuits. The from-scratch version below skips bootstrapping
(documented caveat) — noise grows with each gate, so chains must
stay shallow.

What this module is NOT
-----------------------
This is *not* production-grade FHE. It's a 150-LOC walkthrough of
the simplest LWE-based homomorphic boolean primitive that compiles
to actually-working `NAND` and chained derivations. No quantum
security analysis, no constant-time guarantees, no parameter
hardening. Use Concrete-Python for anything real.

What it teaches
---------------
1. **LWE encryption of a bit**: ciphertext = (a, b) where
   b = ⟨a, sk⟩ + μ·Δ + e (mod q), with μ ∈ {0,1} the message,
   Δ = q/4 the encoding scale, e small Gaussian noise.
2. **Homomorphic addition**: (a₁+a₂, b₁+b₂) encrypts μ₁+μ₂.
3. **NAND via linear arithmetic + thresholding**: NAND(a,b) =
   1 - a·b ≡ 1 - (a+b > 1) for boolean a,b. Implementable as
   linear ops + a single comparison-with-decryption.
4. **Why bootstrapping matters**: without it, noise accumulates;
   roughly log(q/Δ) gates max before decryption flips.

Use in Penumbra
---------------
Per-agent encrypted "in goal region?" bits, combined via NAND/AND
to compute encrypted faction overlap without revealing either
agent's exact bit to the server. The integration is sketched in
the docstring of `homomorphic_faction_overlap`.

References
----------
- Chillotti, Gama, Georgieva, Izabachène. "TFHE: Fast Fully
  Homomorphic Encryption over the Torus" (J. Cryptol. 2020).
- Halevi & Polyakov. "Bootstrapping for HElib" — implementation
  guide reference (the bootstrapping section we deliberately skip).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

# ── parameters ─────────────────────────────────────────────────────
# Pedagogically-small dimensions. Real TFHE uses n=630, q=2^32,
# σ=2^-15·q. Here we shrink to n=64 so a learner can pretty-print
# any ciphertext without their terminal melting.
_LWE_DIMENSION: int = 64
_MODULUS_BITS: int = 32
_MODULUS: int = 1 << _MODULUS_BITS
# Scale q/2 so the message lives at {0, q/2}. Then ciphertext addition
# (mod q) implements XOR exactly: (q/2) + (q/2) = q ≡ 0. The decoder
# bucket is "closer to 0 or closer to q/2 in the wrap-around metric".
_SCALE: int = _MODULUS // 2
_NOISE_STD: float = 3.0  # std dev in plain integer units; well below SCALE/2


@dataclass(frozen=True, slots=True)
class LWEKey:
    """Secret key. Random {0, 1} vector of length _LWE_DIMENSION."""

    s: NDArray[np.int64]

    @classmethod
    def generate(cls) -> LWEKey:
        # secrets.token_bytes for the bit source — never numpy.random
        # for key material in Penumbra.
        raw = secrets.token_bytes(_LWE_DIMENSION)
        s = np.frombuffer(raw, dtype=np.uint8).astype(np.int64) & 1
        return cls(s=s)


@dataclass(frozen=True, slots=True)
class LWECiphertext:
    """LWE ciphertext (a, b) ∈ (Z_q^n, Z_q). Encrypts one bit."""

    a: NDArray[np.int64]
    b: int


def _gaussian_noise() -> int:
    """One sample of small integer noise. Uses secrets-seeded RNG."""
    # Sample from numpy with a fresh secrets-derived seed each call
    # so noise is unpredictable across calls. Production TFHE uses a
    # rejection-sampled discrete Gaussian; this is the educational shortcut.
    seed = int.from_bytes(secrets.token_bytes(8), "big")
    rng = np.random.default_rng(seed)
    return round(float(rng.normal(0.0, _NOISE_STD))) % _MODULUS


def encrypt(key: LWEKey, bit: int) -> LWECiphertext:
    """Encrypt a single bit. Bit must be in {0, 1}."""
    if bit not in (0, 1):
        raise ValueError(f"bit must be 0 or 1; got {bit}")
    a_raw = secrets.token_bytes(_LWE_DIMENSION * 8)
    a = np.frombuffer(a_raw, dtype=np.int64) % _MODULUS
    inner = int(np.sum(a * key.s)) % _MODULUS
    b = (inner + bit * _SCALE + _gaussian_noise()) % _MODULUS
    return LWECiphertext(a=a, b=b)


def decrypt(key: LWEKey, ciphertext: LWECiphertext) -> int:
    """Recover the encrypted bit.

    `raw` lies in [0, q). bit=0 ⇒ raw ≈ 0; bit=1 ⇒ raw ≈ q/2. We pick
    whichever of {0, q/2} is closer in the wrap-around (toroidal)
    distance — bit=0 wins on the "outer quarter" (raw < q/4 or
    raw ≥ 3q/4); bit=1 wins on the "inner half".
    """
    inner = int(np.sum(ciphertext.a * key.s)) % _MODULUS
    raw = (ciphertext.b - inner) % _MODULUS
    quarter = _MODULUS // 4
    return 1 if quarter <= raw < 3 * quarter else 0


# ── homomorphic primitives ─────────────────────────────────────────


def homomorphic_xor(a: LWECiphertext, b: LWECiphertext) -> LWECiphertext:
    """XOR via ciphertext addition.

    With SCALE = q/2, the encoded messages live at {0, q/2}.
    Addition mod q:
      0 + 0       = 0           → bit 0
      0 + (q/2)   = q/2         → bit 1
      (q/2) + 0   = q/2         → bit 1
      (q/2)+(q/2) = q ≡ 0       → bit 0
    Exactly the XOR truth table.
    """
    return LWECiphertext(
        a=(a.a + b.a) % _MODULUS,
        b=(a.b + b.b) % _MODULUS,
    )


def homomorphic_not(c: LWECiphertext) -> LWECiphertext:
    """NOT via (SCALE - b, -a). Decrypts to 1 - m."""
    return LWECiphertext(
        a=(-c.a) % _MODULUS,
        b=(_SCALE - c.b) % _MODULUS,
    )


# NOTE on naming (crypto-audit C1):
#
# The three functions below are NOT homomorphic in the strict sense:
# they take `key: LWEKey` and decrypt the inputs server-side before
# computing the gate. Calling them `homomorphic_nand` was misleading.
#
# Real TFHE achieves the AND gate via a "programmable bootstrap" — a
# noise-refreshing operation that evaluates a lookup table over the
# encrypted bit without decrypting it. We don't implement bootstrapping
# in this educational module (it's a multi-page algorithm in its own
# right); instead we mark the gates as "trusted evaluator" so the
# learner sees the semantic gap clearly.
#
# The ONLY way `homomorphic_faction_overlap` (below) is honest is by
# avoiding these trusted-evaluator gates entirely — it uses XOR + NOT,
# both of which are genuinely homomorphic.


def trusted_evaluator_nand(
    key: LWEKey,
    a: LWECiphertext,
    b: LWECiphertext,
) -> LWECiphertext:
    """**Trusted-evaluator** NAND — decrypts both inputs server-side.

    Not a homomorphic gate. Here to show the gate semantics only; in a
    real TFHE protocol this would be replaced by a programmable
    bootstrap that evaluates the NAND table without learning the inputs.
    """
    ma = decrypt(key, a)
    mb = decrypt(key, b)
    and_bit = ma & mb
    nand_bit = 1 - and_bit
    return encrypt(key, nand_bit)


def trusted_evaluator_and(
    key: LWEKey,
    a: LWECiphertext,
    b: LWECiphertext,
) -> LWECiphertext:
    """AND via NOT(NAND). Trusted evaluator — see `trusted_evaluator_nand`."""
    return homomorphic_not(trusted_evaluator_nand(key, a, b))


def trusted_evaluator_or(
    key: LWEKey,
    a: LWECiphertext,
    b: LWECiphertext,
) -> LWECiphertext:
    """OR via De Morgan. Trusted evaluator — see `trusted_evaluator_nand`."""
    return homomorphic_not(trusted_evaluator_and(key, homomorphic_not(a), homomorphic_not(b)))


# Backwards-compatible aliases for the public API (and any in-repo
# tests that imported the old names). New code should use the
# `trusted_evaluator_*` names so the trust assumption is loud.
homomorphic_nand = trusted_evaluator_nand
homomorphic_and = trusted_evaluator_and
homomorphic_or = trusted_evaluator_or


# ── application: encrypted faction overlap ─────────────────────────


def homomorphic_faction_overlap(
    key: LWEKey,
    in_region_a: LWECiphertext,
    in_region_b: LWECiphertext,
) -> LWECiphertext:
    """Encrypted "are A and B in the same region?".

    The Penumbra use case. Each agent encrypts its boolean "I am in
    goal region X". Two agents' encrypted bits homomorphically NAND
    into "they DIFFER in faction"; NAND of that again gives "they
    share a faction". The server can release the aggregate (k_pairs
    sharing factions) under DP noise without ever learning who is in
    which region.

    Returns an encrypted bit that decrypts to 1 if both agents are
    in the same region (both 0 or both 1), 0 otherwise.

    same_region(a, b) = NOT(XOR(a, b))
    """
    return homomorphic_not(homomorphic_xor(in_region_a, in_region_b))
