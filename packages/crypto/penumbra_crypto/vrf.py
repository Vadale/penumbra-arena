"""Verifiable Random Function — Schnorr-style.

Concept taught: a VRF takes a secret key sk and an input α and produces:
- β = VRF(sk, α): a deterministic pseudorandom output, and
- π: a proof that lets anyone with the public key pk verify β was
  produced by the holder of sk for that exact α.

The output is *uniformly distributed* over the output space (modelled
by the random oracle on the hash) and *biasable only by the secret-key
holder* — and they are *committed* to a single answer per (sk, α) pair
because the proof binds it.

In Penumbra a VRF picks the next block proposer: every validator
computes β_i = VRF(sk_i, "block-N-seed"), and the lowest β wins. The
proof π_i is published so other validators can verify the leader was
chosen fairly. No leader can grind a seed; no other validator can
predict who will win until they see the proofs.

Implementation
- Schnorr-VRF in the same Schnorr group as `educational/pedersen.py`
  and `educational/schnorr.py`, for pedagogical reuse. Production
  Penumbra would use an EC-based VRF (ECVRF-EDWARDS25519-SHA512-TAI
  per RFC 9381) for performance.

References
- Goldberg, Reyzin, Papadopoulos, Včelák. RFC 9381 (2023): VRF.
- Micali, Rabin, Vadhan, "Verifiable random functions" (FOCS 1999).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from penumbra_crypto.educational.pedersen import group_params

_P, _Q, _G, _H = group_params()


@dataclass(frozen=True, slots=True)
class VRFKeypair:
    secret_key: int
    public_key: int  # = g^secret_key mod p


@dataclass(frozen=True, slots=True)
class VRFOutput:
    """The VRF output bytes plus the proof transcript."""

    beta: bytes
    proof: VRFProof


@dataclass(frozen=True, slots=True)
class VRFProof:
    """Schnorr-VRF proof: (gamma, c, s) — fixed-length integers in Z_q."""

    gamma: int  # = sk * h_alpha    (kept as a group element via exponent)
    c: int
    s: int


def keygen() -> VRFKeypair:
    """Fresh VRF keypair. sk ←R Z_q; pk = g^sk mod p."""
    sk = secrets.randbelow(_Q - 1) + 1
    pk = pow(_G, sk, _P)
    return VRFKeypair(secret_key=sk, public_key=pk)


def _hash_to_group(alpha: bytes) -> int:
    """Map `alpha` deterministically to a group element h_α = g^(H(α) mod q).

    Not a constant-time, side-channel-safe hash-to-curve (the Penumbra
    educational stack does not need to defend against side channels in
    offline-only code). RFC 9381's "try-and-increment" is the
    production-grade alternative.
    """
    digest = hashlib.sha256(b"penumbra-vrf-h2g:" + alpha).digest()
    exponent = int.from_bytes(digest, "big") % _Q
    return pow(_G, exponent, _P)


def prove(secret_key: int, alpha: bytes) -> VRFOutput:
    """Produce (β, π) for the given input α under `secret_key`.

    β is derived from γ = h_α^sk (a deterministic function of sk and α)
    by hashing. π is a Schnorr proof that γ was computed correctly.
    """
    h_alpha = _hash_to_group(alpha)
    gamma = pow(h_alpha, secret_key, _P)

    # Schnorr proof: prove knowledge of sk s.t. g^sk = pk AND h_alpha^sk = gamma.
    # This is a "DDH tuple" proof: one challenge, two commitments.
    k = secrets.randbelow(_Q - 1) + 1
    u = pow(_G, k, _P)  # commitment in the g basis
    v = pow(h_alpha, k, _P)  # commitment in the h_alpha basis
    c = _challenge(alpha, h_alpha, gamma, u, v)
    s = (k + c * secret_key) % _Q

    beta = hashlib.sha256(b"penumbra-vrf-out:" + gamma.to_bytes(256, "big")).digest()
    return VRFOutput(beta=beta, proof=VRFProof(gamma=gamma, c=c, s=s))


def verify(public_key: int, alpha: bytes, output: VRFOutput) -> bool:
    """Check (β, π) for `alpha` under `public_key`."""
    h_alpha = _hash_to_group(alpha)
    gamma = output.proof.gamma
    c = output.proof.c
    s = output.proof.s

    if not (0 < gamma < _P and 0 <= s < _Q):
        return False

    # Reconstruct u, v from (s, c) and the public values.
    # u = g^s · pk^{-c}    v = h_alpha^s · gamma^{-c}
    u = (pow(_G, s, _P) * pow(public_key, _Q - c, _P)) % _P  # pk^{-c} via Fermat
    v = (pow(h_alpha, s, _P) * pow(gamma, _Q - c, _P)) % _P

    expected_c = _challenge(alpha, h_alpha, gamma, u, v)
    if expected_c != c:
        return False

    expected_beta = hashlib.sha256(b"penumbra-vrf-out:" + gamma.to_bytes(256, "big")).digest()
    # Crypto-audit closure: constant-time compare. β is public in
    # Penumbra's leader-election path, but the VRF module is general-
    # purpose — anyone who repurposes it for a secret β would otherwise
    # leak a timing oracle on the first mismatching byte.
    return hmac.compare_digest(expected_beta, output.beta)


def _challenge(alpha: bytes, h_alpha: int, gamma: int, u: int, v: int) -> int:
    h = hashlib.sha256()
    h.update(b"penumbra-vrf-challenge")
    h.update(alpha)
    h.update(h_alpha.to_bytes(256, "big"))
    h.update(gamma.to_bytes(256, "big"))
    h.update(u.to_bytes(256, "big"))
    h.update(v.to_bytes(256, "big"))
    return int.from_bytes(h.digest(), "big") % _Q
