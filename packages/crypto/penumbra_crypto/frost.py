"""FROST: Flexible Round-Optimised Schnorr Threshold signatures.

Concept taught: a t-of-n threshold Schnorr signature lets any subset of
size at least t out of n participants produce ONE Schnorr signature that
verifies under a single aggregated public key Y = g^x, where x is shared
via Shamir among the n parties. No single party (not even t-1 colluding
ones) can sign alone, yet the signature is indistinguishable on the wire
from a vanilla Schnorr.

Why Schnorr threshold matters
-----------------------------
- Bitcoin Lightning, Coinbase MPC custody, Frostsnap wallets — FROST is
  the production threshold scheme of 2024-25.
- Linearity of Schnorr's response equation (s = k + c·x) makes the
  threshold variant clean: each signer contributes a partial s_i, and
  the aggregator combines them with Lagrange coefficients.

Round-optimised flavour (FROST-2)
---------------------------------
- Round 1 (offline): each signer commits to a per-signature nonce by
  publishing D_i = g^d_i and E_i = g^e_i.
- Round 2 (online): given the message and the participating subset,
  every signer locally computes their binding factor ρ_i, response
  share z_i, and the aggregator sums {z_i} into one final s.

The implementation below is fully self-contained over the same Schnorr
group used by the educational Pedersen/Schnorr modules so it composes
cleanly with the rest of the offline-only stack. A production deployment
would target secp256k1 + BIP-340 tagged hashes.

References
----------
- Komlo, Goldberg, "FROST: Flexible Round-Optimised Schnorr Threshold
  Signatures" (SAC 2020).
- IRTF draft-irtf-cfrg-frost-15.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from penumbra_crypto.educational.pedersen import group_params

_P, _Q, _G, _H = group_params()


def _shamir_split_in_q(secret: int, *, n: int, t: int) -> list[tuple[int, int]]:
    """Shamir split in Z_q over the Schnorr-group order q.

    Local helper because ``educational.shamir`` works over a fixed
    256-bit prime that is too small for the 2048-bit safe-prime group
    Penumbra uses for Schnorr/FROST. Same Horner-rule evaluation, just
    a different modulus.
    """
    coeffs = [secret % _Q] + [secrets.randbelow(_Q - 1) + 1 for _ in range(t - 1)]
    out: list[tuple[int, int]] = []
    for x in range(1, n + 1):
        y = 0
        for c in reversed(coeffs):
            y = (y * x + c) % _Q
        out.append((x, y))
    return out


class FROSTError(RuntimeError):
    """Base class for FROST protocol failures (rogue indices, etc.)."""


@dataclass(frozen=True, slots=True)
class FROSTShare:
    """One participant's secret share + their public participant index."""

    index: int
    secret_share: int  # P(index) where P(0) = group secret
    group_public_key: int  # Y = g^x, shared across participants


@dataclass(frozen=True, slots=True)
class NonceCommitment:
    """Per-signature commitment from a participant (D_i, E_i)."""

    index: int
    d_commit: int  # g^d_i mod p
    e_commit: int  # g^e_i mod p


@dataclass(frozen=True, slots=True)
class NonceWitness:
    """Secret nonce pair held by the signer between rounds (d_i, e_i)."""

    index: int
    d: int
    e: int


@dataclass(frozen=True, slots=True)
class SignatureShare:
    """Partial signature contribution z_i sent to the aggregator."""

    index: int
    z: int


@dataclass(frozen=True, slots=True)
class FROSTSignature:
    """Final Schnorr signature: (R, s). Verified as plain Schnorr."""

    r_commit: int  # R = g^k mod p
    s: int  # response in Z_q


# ── key generation (trusted-dealer Shamir) ────────────────────────


def keygen(*, n: int, t: int) -> list[FROSTShare]:
    """Sample x ←R Z_q, split into n Shamir shares, return per-party shares.

    Returns a list of `FROSTShare` whose `secret_share` are P(1)…P(n) of a
    degree (t-1) polynomial with P(0) = x. The group public key is
    Y = g^x mod p, identical across all returned shares.

    This is the trusted-dealer setup; FROST also supports a fully
    distributed DKG (Pedersen 1991), out of scope for the pedagogical
    module.
    """
    if not 1 <= t <= n:
        raise FROSTError(f"need 1 <= t <= n; got t={t}, n={n}")
    x = secrets.randbelow(_Q - 1) + 1
    y = pow(_G, x, _P)
    raw_shares = _shamir_split_in_q(x, n=n, t=t)
    return [FROSTShare(index=i, secret_share=s, group_public_key=y) for (i, s) in raw_shares]


# ── round 1 — nonce commitment ────────────────────────────────────


def commit_nonces(index: int) -> tuple[NonceCommitment, NonceWitness]:
    """Sample (d_i, e_i) ←R Z_q and publish (D_i = g^d_i, E_i = g^e_i).

    The signer retains the witness (d_i, e_i) for round 2. Nonces MUST be
    used at most once per signature — reusing them collapses Schnorr's
    response equation into a system whose solution leaks the secret share.
    """
    d = secrets.randbelow(_Q - 1) + 1
    e = secrets.randbelow(_Q - 1) + 1
    commit = NonceCommitment(
        index=index,
        d_commit=pow(_G, d, _P),
        e_commit=pow(_G, e, _P),
    )
    return commit, NonceWitness(index=index, d=d, e=e)


# ── round 2 — partial sign + aggregate ────────────────────────────


def _binding_factor(index: int, message: bytes, commitments: list[NonceCommitment]) -> int:
    """Per-signer binding factor ρ_i = H("ρ" || i || msg || all commitments) mod q.

    The binding factor is what makes FROST-2 secure against the
    Drijvers-style sub-exponential forgery on naive 2-round threshold
    Schnorr; every signer's effective nonce becomes
    D_i · E_i^{ρ_i}, which is non-linear in ρ_i.
    """
    h = hashlib.sha256()
    h.update(b"penumbra-frost-rho-v1")
    h.update(index.to_bytes(4, "big"))
    h.update(message)
    for c in commitments:
        h.update(c.index.to_bytes(4, "big"))
        h.update(c.d_commit.to_bytes(256, "big"))
        h.update(c.e_commit.to_bytes(256, "big"))
    return int.from_bytes(h.digest(), "big") % _Q


def _group_commitment(message: bytes, commitments: list[NonceCommitment]) -> int:
    """R = Π_i (D_i · E_i^{ρ_i}) mod p — the aggregate nonce commitment."""
    r = 1
    for c in commitments:
        rho = _binding_factor(c.index, message, commitments)
        r = (r * c.d_commit * pow(c.e_commit, rho, _P)) % _P
    return r


def _challenge(group_public_key: int, group_commit: int, message: bytes) -> int:
    """Schnorr challenge c = H(R || Y || msg) mod q (Fiat-Shamir)."""
    h = hashlib.sha256()
    h.update(b"penumbra-frost-challenge-v1")
    h.update(group_commit.to_bytes(256, "big"))
    h.update(group_public_key.to_bytes(256, "big"))
    h.update(message)
    return int.from_bytes(h.digest(), "big") % _Q


def _lagrange_coefficient(index: int, signer_indices: list[int]) -> int:
    """λ_i(0) at participant i over the active set, in Z_q."""
    num, den = 1, 1
    for j in signer_indices:
        if j == index:
            continue
        num = (num * (-j)) % _Q
        den = (den * (index - j)) % _Q
    return (num * pow(den, _Q - 2, _Q)) % _Q


def sign_share(
    share: FROSTShare,
    witness: NonceWitness,
    message: bytes,
    commitments: list[NonceCommitment],
) -> SignatureShare:
    """Compute participant i's contribution z_i = d_i + e_i·ρ_i + λ_i·s_i·c mod q.

    `commitments` is the full ordered list of nonce commitments from the
    active signer set (must include this signer's own commitment).
    """
    if share.index != witness.index:
        raise FROSTError("share and witness indices disagree")
    signer_indices = [c.index for c in commitments]
    if share.index not in signer_indices:
        raise FROSTError(f"signer {share.index} not in active set {signer_indices}")
    rho = _binding_factor(share.index, message, commitments)
    group_commit = _group_commitment(message, commitments)
    c = _challenge(share.group_public_key, group_commit, message)
    lam = _lagrange_coefficient(share.index, signer_indices)
    z = (witness.d + witness.e * rho + lam * share.secret_share * c) % _Q
    return SignatureShare(index=share.index, z=z)


def aggregate(
    shares: list[SignatureShare],
    commitments: list[NonceCommitment],
    message: bytes,
) -> FROSTSignature:
    """Sum partial signature shares into (R, s).

    The aggregator does not learn any secret beyond what was already
    public: R is the group commitment, s is the sum of contributions.
    """
    if {s.index for s in shares} != {c.index for c in commitments}:
        raise FROSTError("signature shares and commitments cover different signers")
    r = _group_commitment(message, commitments)
    s_total = 0
    for sh in shares:
        s_total = (s_total + sh.z) % _Q
    return FROSTSignature(r_commit=r, s=s_total)


# ── verifier — plain Schnorr ──────────────────────────────────────


def verify(group_public_key: int, message: bytes, signature: FROSTSignature) -> bool:
    """Verify (R, s) as a plain Schnorr signature under Y.

    Accepts iff g^s ≡ R · Y^c (mod p), with c = H(R || Y || msg). The
    threshold structure is INVISIBLE to the verifier — that is FROST's
    headline property.
    """
    if not (0 < signature.r_commit < _P and 0 <= signature.s < _Q):
        return False
    c = _challenge(group_public_key, signature.r_commit, message)
    lhs = pow(_G, signature.s, _P)
    rhs = (signature.r_commit * pow(group_public_key, c, _P)) % _P
    return hmac.compare_digest(lhs.to_bytes(256, "big"), rhs.to_bytes(256, "big"))


# ── demo ──────────────────────────────────────────────────────────


def demo(*, n: int = 5, t: int = 3) -> dict[str, object]:
    """End-to-end FROST demo + tamper test, returned as a JSON-safe dict."""
    n = max(2, min(int(n), 9))
    t = max(2, min(int(t), n))
    shares = keygen(n=n, t=t)
    active = shares[:t]
    commits_witnesses = [commit_nonces(s.index) for s in active]
    commits = [cw[0] for cw in commits_witnesses]
    witnesses = [cw[1] for cw in commits_witnesses]
    msg = b"penumbra-frost-demo-message"

    sig_shares = [sign_share(s, w, msg, commits) for s, w in zip(active, witnesses, strict=True)]
    signature = aggregate(sig_shares, commits, msg)
    honest_ok = verify(shares[0].group_public_key, msg, signature)
    tampered_ok = verify(shares[0].group_public_key, b"tampered-message", signature)
    forged = FROSTSignature(r_commit=signature.r_commit, s=(signature.s + 1) % _Q)
    forged_ok = verify(shares[0].group_public_key, msg, forged)

    return {
        "available": True,
        "algorithm": "FROST (round-optimised threshold Schnorr)",
        "n_signers": n,
        "threshold": t,
        "group_public_key_short": format(shares[0].group_public_key, "x")[:32],
        "signature_r_short": format(signature.r_commit, "x")[:32],
        "signature_s_short": format(signature.s, "x")[:32],
        "honest_verifies": bool(honest_ok),
        "tampered_message_verifies": bool(tampered_ok),
        "tampered_signature_verifies": bool(forged_ok),
        "signers_used": [s.index for s in active],
    }
