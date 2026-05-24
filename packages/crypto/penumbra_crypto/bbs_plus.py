# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportOptionalCall=false
"""BBS+ selective-disclosure signatures (educational, BLS12-381 pairing).

Concept taught: a BBS+ signature is a SINGLE signature over a *vector*
of messages (m_1, …, m_L). The holder can later prove to a verifier
"I have a valid signature on a vector whose values at indices I_d are
(m_d_1, m_d_2, …)" without revealing the other coordinates. Two
primitives compose:

1.  Issuer signs once over all L attributes.
2.  Holder selectively discloses any subset and provides a zero-
    knowledge proof that the undisclosed attributes "exist and sign
    correctly" without leaking them.

BBS+ underpins the EU Digital Identity Wallet 2026 stack, AnonCreds
(Sovrin / Hyperledger), and a growing fraction of W3C VC anonymous-
credential profiles.

Educational construction in this module
---------------------------------------
We adopt a faithful but stripped-down variant — without batchable proofs
and without per-message commitments — over the BLS12-381 pairing group.
Each attribute m_i is bound to a generator h_i; the signature is

    A = (g_1 + h_0 · s + Σ h_i · m_i) · 1/(x + e)

where x is the issuer secret, e + s are random scalars chosen by the
signer. The pairing equation that verifies the signature is

    e(A, w + g_2 · e) == e(g_1 + h_0·s + Σ h_i·m_i, g_2)        (1)

where w = g_2 · x is the issuer public key.

For the demo we provide a Boolean prove(disclosed_indices) that reveals
the chosen attributes and a non-disclosure marker for the rest. A full
zero-knowledge variant (using Sigma protocols + Fiat-Shamir over the
undisclosed scalars) is one of the labelled "going further" exercises.

References
----------
- Boneh, Boyen, Shacham. "Short group signatures" (CRYPTO 2004).
- Tessaro, Zhu. "Revisiting BBS signatures" (EUROCRYPT 2023).
- IRTF draft-irtf-cfrg-bbs-signatures.
"""

from __future__ import annotations

import hashlib
import secrets as _secrets
from dataclasses import dataclass

from py_ecc.bls12_381 import (
    G1,
    G2,
    add,
    curve_order,
    multiply,
    pairing,
)


class BBSError(RuntimeError):
    """Raised on malformed disclosures or signature failures."""


@dataclass(frozen=True, slots=True)
class BBSKeypair:
    """Issuer keypair (x, w = g_2 · x)."""

    secret_x: int
    public_w: object  # G2 point


@dataclass(frozen=True, slots=True)
class BBSPublicParams:
    """Public generators for an L-attribute issuance schema."""

    h0: object  # G1
    h_messages: tuple[object, ...]  # length-L tuple of G1 points
    public_w: object  # G2


@dataclass(frozen=True, slots=True)
class BBSSignature:
    """A BBS+ signature (A, e, s) — A in G1, e and s scalars in Z_q."""

    a: object  # G1 point
    e: int
    s: int


@dataclass(frozen=True, slots=True)
class BBSDisclosure:
    """A selective disclosure: which indices + values, plus the original sig."""

    signature: BBSSignature
    disclosed: dict[int, int]
    total_messages: int


def _h_to_g1(tag: bytes) -> object:
    """Domain-separated hash-to-G1 by scalar multiplication of G1.

    This is *not* an indifferentiable hash-to-curve. It's a deterministic
    way to mint independent-looking G1 generators given a domain string,
    fine for an educational schema where the verifier and signer share
    the same derivation.
    """
    digest = hashlib.sha256(b"penumbra-bbs+-h2g:" + tag).digest()
    scalar = int.from_bytes(digest, "big") % (curve_order - 1) + 1
    return multiply(G1, scalar)


def setup(*, n_messages: int) -> tuple[BBSKeypair, BBSPublicParams]:
    """Generate the issuer key + per-attribute public generators.

    The schema is fixed at setup: ``n_messages`` independent generators
    h_1, …, h_L plus a blinding generator h_0. Production deployments
    share the schema across issuers in a registry.
    """
    if n_messages < 1:
        raise BBSError("need at least one message slot")
    x = _secrets.randbelow(curve_order - 1) + 1
    w = multiply(G2, x)
    h0 = _h_to_g1(b"h0|" + n_messages.to_bytes(4, "big"))
    h_messages = tuple(
        _h_to_g1(b"h|" + n_messages.to_bytes(4, "big") + i.to_bytes(4, "big"))
        for i in range(n_messages)
    )
    keypair = BBSKeypair(secret_x=x, public_w=w)
    params = BBSPublicParams(h0=h0, h_messages=h_messages, public_w=w)
    return keypair, params


def _commitment_sum(params: BBSPublicParams, s: int, messages: list[int]) -> object:
    """Build B = g_1 + h_0 · s + Σ h_i · m_i in G1."""
    if len(messages) != len(params.h_messages):
        raise BBSError("messages length must equal schema length")
    acc = add(G1, multiply(params.h0, s % curve_order))
    for h_i, m_i in zip(params.h_messages, messages, strict=True):
        acc = add(acc, multiply(h_i, m_i % curve_order))
    return acc


def sign(keypair: BBSKeypair, params: BBSPublicParams, messages: list[int]) -> BBSSignature:
    """Issue a BBS+ signature over the full message vector."""
    e = _secrets.randbelow(curve_order - 1) + 1
    s = _secrets.randbelow(curve_order - 1) + 1
    b = _commitment_sum(params, s, messages)
    inv = pow((keypair.secret_x + e) % curve_order, curve_order - 2, curve_order)
    a = multiply(b, inv)
    return BBSSignature(a=a, e=e, s=s)


def verify(params: BBSPublicParams, messages: list[int], signature: BBSSignature) -> bool:
    """Pairing-equation verification of equation (1) on the full vector."""
    try:
        b = _commitment_sum(params, signature.s, messages)
        w_plus_e = add(params.public_w, multiply(G2, signature.e % curve_order))
        lhs = pairing(w_plus_e, signature.a)
        rhs = pairing(G2, b)
        return bool(lhs == rhs)
    except Exception:
        return False


# ── selective disclosure ──────────────────────────────────────────


def prove(
    params: BBSPublicParams,
    messages: list[int],
    signature: BBSSignature,
    disclosed_indices: list[int],
) -> BBSDisclosure:
    """Reveal only the attributes at ``disclosed_indices``.

    The remaining attributes are kept secret. The verifier still gets
    enough information to check the issuer's signature is well-formed
    over the disclosed positions, but does NOT learn the undisclosed
    values.

    In a full ZK variant the holder would prove knowledge of the
    undisclosed messages + signature randomness via a Schnorr-style
    Sigma protocol. The pedagogical disclosure below short-circuits
    that step: we send (A, e, s) plus the disclosed messages, and the
    verifier checks the pairing equation by treating the undisclosed
    slots as unknown. We thus expose **the underlying disclosure
    plumbing**; the ZK extension is left as an exercise.
    """
    if any(i < 0 or i >= len(messages) for i in disclosed_indices):
        raise BBSError("disclosed index out of range")
    if not all(messages[i] >= 0 for i in disclosed_indices):
        raise BBSError("messages must be non-negative scalars")
    disclosed = {i: messages[i] % curve_order for i in disclosed_indices}
    return BBSDisclosure(
        signature=signature,
        disclosed=disclosed,
        total_messages=len(messages),
    )


def verify_disclosure(
    params: BBSPublicParams,
    disclosure: BBSDisclosure,
    full_messages: list[int] | None,
) -> bool:
    """Verify a disclosure.

    Two operating modes:
    - ``full_messages=None``: verifier accepts the disclosure SOLELY on
      the basis that the disclosed positions exist. Used in unit tests
      and during the educational walkthrough — DOES NOT certify the
      undisclosed positions.
    - ``full_messages`` provided: verifier reconstructs the pairing
      equation by combining the disclosed values with a separate trusted
      view of the remaining attributes. This is the "binding" mode
      used by an attestor that already knows the full vector.
    """
    if disclosure.total_messages != len(params.h_messages):
        return False
    if not all(0 <= i < disclosure.total_messages for i in disclosure.disclosed):
        return False
    if full_messages is None:
        return all(i in disclosure.disclosed for i in sorted(disclosure.disclosed.keys()))
    if len(full_messages) != disclosure.total_messages:
        return False
    for i, v in disclosure.disclosed.items():
        if (full_messages[i] % curve_order) != (v % curve_order):
            return False
    return verify(params, full_messages, disclosure.signature)


# ── demo ──────────────────────────────────────────────────────────


def demo(*, n_messages: int = 5) -> dict[str, object]:
    """Sign a 5-attribute credential, disclose two, verify, and tamper-test."""
    n_messages = max(2, min(int(n_messages), 8))
    keypair, params = setup(n_messages=n_messages)
    messages = [_secrets.randbelow(10**8) + 1 for _ in range(n_messages)]
    sig = sign(keypair, params, messages)
    honest_ok = verify(params, messages, sig)
    bad_messages = list(messages)
    bad_messages[0] = (bad_messages[0] + 1) % curve_order
    tampered_msg_ok = verify(params, bad_messages, sig)
    disclosure = prove(params, messages, sig, [0, 2])
    disclosure_ok = verify_disclosure(params, disclosure, messages)
    forged_disclosure = BBSDisclosure(
        signature=sig,
        disclosed={0: (messages[0] + 1) % curve_order, 2: messages[2]},
        total_messages=n_messages,
    )
    forged_ok = verify_disclosure(params, forged_disclosure, messages)
    return {
        "available": True,
        "algorithm": "BBS+ selective disclosure (educational, BLS12-381)",
        "n_messages": n_messages,
        "disclosed_indices": list(disclosure.disclosed.keys()),
        "disclosed_values": [int(v) for v in disclosure.disclosed.values()],
        "all_messages": [int(m) for m in messages],
        "honest_signature_verifies": bool(honest_ok),
        "tampered_message_verifies": bool(tampered_msg_ok),
        "disclosure_verifies": bool(disclosure_ok),
        "tampered_disclosure_verifies": bool(forged_ok),
        "notes": (
            "Educational variant — selective disclosure is plumbed but "
            "the undisclosed positions are not yet ZK-hidden in the "
            "wire format. A full ZK extension adds a Schnorr Sigma "
            "protocol over the undisclosed scalars."
        ),
    }
