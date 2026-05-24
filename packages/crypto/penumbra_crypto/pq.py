"""Post-quantum key encapsulation and signatures.

Concept taught: lattice-based cryptography survives Shor's algorithm.
Classical RSA / ECC fall to a future cryptographically-relevant quantum
computer; ML-KEM and ML-DSA do not (or at least, no known polynomial-time
quantum algorithm breaks them).

Penumbra uses:
- **ML-KEM-768** (NIST FIPS 203; formerly CRYSTALS-Kyber-768) — key
  encapsulation. Each agent establishes a session key with the server
  via a single round trip: server publishes a public key, agent runs
  `encapsulate(pk) → (ct, shared_secret)`, server runs
  `decapsulate(sk, ct) → shared_secret`. ~128-bit security against
  both classical and quantum adversaries.
- **ML-DSA-65** (NIST FIPS 204; formerly CRYSTALS-Dilithium-3) —
  signatures. Each agent signs its action with its Dilithium private
  key; validators verify on the way in.

Why not "Kyber"/"Dilithium" in the API? NIST renamed them at
standardisation (Aug 2024); `pqcrypto` follows the FIPS names. They are
the same algorithms.

References
----------
- NIST FIPS 203: Module-Lattice-Based Key-Encapsulation Mechanism Standard.
- NIST FIPS 204: Module-Lattice-Based Digital Signature Standard.
- pqcrypto: https://pypi.org/project/pqcrypto/
"""

from __future__ import annotations

from dataclasses import dataclass

# NIST FIPS 203 (Kyber-3 post-standardisation)
from pqcrypto.kem.ml_kem_768 import (
    decrypt as _kem_decapsulate,
)
from pqcrypto.kem.ml_kem_768 import (
    encrypt as _kem_encapsulate,
)
from pqcrypto.kem.ml_kem_768 import (
    generate_keypair as _kem_keypair,
)

# NIST FIPS 204 (Dilithium-3 post-standardisation)
from pqcrypto.sign.ml_dsa_65 import (
    generate_keypair as _sig_keypair,
)
from pqcrypto.sign.ml_dsa_65 import (
    sign as _sig_sign,
)
from pqcrypto.sign.ml_dsa_65 import (
    verify as _sig_verify,
)

from penumbra_crypto.bls import wipe


@dataclass(frozen=True, slots=True)
class KEMKeypair:
    """ML-KEM-768 keypair. `secret_key` MUST stay on the originator's host."""

    public_key: bytes
    secret_key: bytes


@dataclass(frozen=True, slots=True)
class KEMResult:
    """Output of `encapsulate`: a ciphertext to ship, plus a shared secret."""

    ciphertext: bytes
    shared_secret: bytes


@dataclass(frozen=True, slots=True)
class SigKeypair:
    """ML-DSA-65 keypair. `secret_key` MUST stay on the signer's host."""

    public_key: bytes
    secret_key: bytes


# ── ML-KEM-768 (Kyber-3) ──────────────────────────────────────────


def kem_keygen() -> KEMKeypair:
    """Generate a fresh ML-KEM-768 keypair."""
    pk, sk = _kem_keypair()
    return KEMKeypair(public_key=pk, secret_key=sk)


def kem_encapsulate(public_key: bytes) -> KEMResult:
    """Encapsulate a shared secret against `public_key`.

    Returns the ciphertext to ship to the holder of `secret_key` plus the
    32-byte shared secret. The caller is responsible for *using* the
    shared secret to key a symmetric channel (e.g. an AEAD).
    """
    ciphertext, shared_secret = _kem_encapsulate(public_key)
    return KEMResult(ciphertext=ciphertext, shared_secret=shared_secret)


def kem_decapsulate(secret_key: bytes, ciphertext: bytes) -> bytes:
    """Recover the shared secret from a KEM ciphertext.

    The underlying library implements implicit rejection: invalid or
    tampered ciphertexts return a deterministic *but unpredictable*
    32-byte string rather than raising. Callers must therefore include
    an authenticated transcript or compare-and-MAC the shared secret
    before treating decapsulation as success.

    Crypto-audit closure: a transient bytearray copy of the secret key
    is wiped before this function returns. The caller's original
    ``secret_key`` bytes object is immutable and unaffected; deeper
    zeroization would require the underlying ``pqcrypto`` C buffer to
    be locked + scrubbed, which is out of scope for the educational
    stack.
    """
    sk_buffer = bytearray(secret_key)
    try:
        return _kem_decapsulate(bytes(sk_buffer), ciphertext)
    finally:
        wipe(sk_buffer)


# ── ML-DSA-65 (Dilithium-3) ───────────────────────────────────────


def sig_keygen() -> SigKeypair:
    """Generate a fresh ML-DSA-65 keypair."""
    pk, sk = _sig_keypair()
    return SigKeypair(public_key=pk, secret_key=sk)


def sign(secret_key: bytes, message: bytes) -> bytes:
    """Detached ML-DSA-65 signature over `message`.

    `pqcrypto`'s underlying API returns the signature attached to the
    message; we keep only the signature bytes for the wire format.

    Crypto-audit closure: a transient bytearray copy of the secret key
    is wiped before this function returns.
    """
    sk_buffer = bytearray(secret_key)
    try:
        return _sig_sign(bytes(sk_buffer), message)
    finally:
        wipe(sk_buffer)


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Verify `signature` is a valid ML-DSA-65 sig on `message` under `public_key`.

    Returns `True` for valid signatures, `False` otherwise. `pqcrypto`'s
    underlying verify returns a bool and does not raise on malformed
    inputs, so a wrong-length or fully-zero signature is rejected cleanly
    here (returns False). Any unexpected exception is also treated as
    rejection so callers can rely on the False branch.
    """
    try:
        return bool(_sig_verify(public_key, message, signature))
    except Exception:
        return False


class PQError(RuntimeError):
    """Base class for post-quantum crypto failures."""
