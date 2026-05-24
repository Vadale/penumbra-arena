"""BLS aggregate signatures on BLS12-381 with rogue-key defence.

Concept taught: a BLS signature is one G2 point per signer. Aggregating
sigs is *addition* of those points; aggregating pubkeys is addition of
their G1 points. Verifying an aggregate against the aggregate pubkey is
**one pairing equation** regardless of how many signers participated —
the dramatic constant-time-in-n property that makes BLS attractive for
blockchain consensus (Penumbra Phase 3 uses it for validator quorums).

The rogue-key attack: an adversary chooses their public key as
pk' = pk_real - Σ pk_others, and then the aggregate sig for "all
signed this" trivially decomposes into a forgery. The defence is
**proof of possession**: each validator publishes a BLS signature
PoP_i over a domain-tagged message containing their own pubkey, proving
they hold the corresponding secret key. Validators that fail PoP at
registration cannot participate.

Implementation
- Wraps `py_ecc.bls.G2ProofOfPossession` (the IETF BLS spec for the
  PoP variant; same scheme as Ethereum 2 consensus).
- BLS12-381 curve, 128-bit security.

References
- Boneh, Lynn, Shacham. "Short signatures from the Weil pairing"
  (J. Crypt. 2001).
- Boneh, Drijvers, Neven. "Compact multi-signatures for smaller
  blockchains" (ASIACRYPT 2018). The rogue-key defence.
- IETF draft-irtf-cfrg-bls-signature.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Final, cast

from eth_typing import BLSPubkey, BLSSignature
from py_ecc.bls.ciphersuites import G2ProofOfPossession as _bls  # noqa: N813

PUBLIC_KEY_BYTES: Final[int] = 48
SIGNATURE_BYTES: Final[int] = 96

_logger = logging.getLogger(__name__)


def wipe(key: bytes | bytearray) -> None:
    """Best-effort zeroization of a secret-key buffer.

    Crypto-audit closure: Python's ``bytes`` is immutable, so once an
    object is created its memory cannot be overwritten in place — the
    most an interpreter-level helper can do is overwrite a ``bytearray``
    backing buffer and log a no-op warning for the immutable case. This
    helper exists so callers ALWAYS reach for the same wipe primitive
    instead of inlining whichever subset they remember.

    Behaviour
    ---------
    - ``bytearray``: every byte set to 0 via slice-assignment.
    - ``bytes``: a no-op + a debug log; documented limitation. A real
      deployment would store secrets in a ``mlocked`` buffer wrapped in
      a ``ctypes``-backed bytearray or, better, never let secret bytes
      land in a Python object at all (Rust/Go workers, HSM).
    """
    if isinstance(key, bytearray):
        for i in range(len(key)):
            key[i] = 0
        return
    _logger.debug("wipe(bytes) is a no-op: Python's immutable bytes cannot be zeroized in place")


@dataclass(frozen=True, slots=True)
class BLSKeypair:
    """Secret + public key for BLS-on-BLS12-381.

    `secret_key` is a 32-byte big-endian integer in [1, curve_order).
    `public_key` is a 48-byte compressed G1 point.
    """

    secret_key: bytes
    public_key: bytes


def keygen() -> BLSKeypair:
    """Generate a fresh BLS keypair from 32 bytes of CSPRNG entropy.

    Crypto-audit closure: the IKM bytearray that seeds the IETF KeyGen
    is wiped before the function returns; only the final ``sk_bytes``
    (which must escape into the returned dataclass) survives.
    """
    ikm = bytearray(secrets.token_bytes(32))
    try:
        sk_int = _bls.KeyGen(bytes(ikm))
        sk_bytes = sk_int.to_bytes(32, "big")
        pk = _bls.SkToPk(sk_int)
        return BLSKeypair(secret_key=sk_bytes, public_key=pk)
    finally:
        wipe(ikm)


def sign(secret_key: bytes, message: bytes) -> bytes:
    """Produce a 96-byte BLS signature on `message`.

    Crypto-audit closure: any local bytearray copy of the secret key is
    wiped before this function returns so the secret does not linger in
    Python's heap longer than the underlying signing primitive needs.
    """
    sk_buffer = bytearray(secret_key)
    try:
        sk_int = int.from_bytes(sk_buffer, "big")
        return _bls.Sign(sk_int, message)
    finally:
        wipe(sk_buffer)


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Verify a BLS signature. Returns False on any malformed input."""
    try:
        return bool(
            _bls.Verify(cast(BLSPubkey, public_key), message, cast(BLSSignature, signature))
        )
    except Exception:
        return False


def aggregate_signatures(signatures: list[bytes]) -> bytes:
    """Combine N BLS sigs into one 96-byte aggregate.

    The aggregate is the group sum of the individual G2 sig points. Each
    validator can locally compute the aggregate without revealing their
    secret key.
    """
    if not signatures:
        raise ValueError("cannot aggregate zero signatures")
    return _bls.Aggregate([cast(BLSSignature, s) for s in signatures])


def fast_aggregate_verify(
    public_keys: list[bytes],
    message: bytes,
    aggregate_signature: bytes,
) -> bool:
    """Verify aggregate-sig case where ALL signers signed the SAME message.

    This is the Penumbra block-finality use case: validators sign the
    block hash. Returns False on any malformed input.
    """
    try:
        return bool(
            _bls.FastAggregateVerify(
                [cast(BLSPubkey, pk) for pk in public_keys],
                message,
                cast(BLSSignature, aggregate_signature),
            )
        )
    except Exception:
        return False


# ── proof of possession (rogue-key defence) ────────────────────────


def prove_possession(secret_key: bytes) -> bytes:
    """Produce a PoP: BLS signature over a domain-tagged version of the pubkey.

    The signature is over the prover's own pubkey, salted by the
    IETF-defined POP_TAG. A holder of the *secret* key can produce it;
    no one else can. Crucially this signature is over the *attacker's*
    pubkey — so a rogue-key adversary cannot just borrow other parties'
    PoPs to register a synthetic pubkey.
    """
    sk_buffer = bytearray(secret_key)
    try:
        sk_int = int.from_bytes(sk_buffer, "big")
        return _bls.PopProve(sk_int)
    finally:
        wipe(sk_buffer)


def verify_possession(public_key: bytes, pop: bytes) -> bool:
    """Verify a proof of possession. Required at validator registration."""
    try:
        return bool(_bls.PopVerify(cast(BLSPubkey, public_key), cast(BLSSignature, pop)))
    except Exception:
        return False


class BLSError(RuntimeError):
    """Raised when a BLS operation fails in an unexpected way."""
