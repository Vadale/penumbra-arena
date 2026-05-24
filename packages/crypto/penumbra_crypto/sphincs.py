"""SPHINCS+ stateless hash-based post-quantum signatures.

Concept taught: SPHINCS+ derives its post-quantum security from one
assumption only — the collision/preimage resistance of a hash function.
No lattices, no codes, no isogenies. The cost is large signatures
(~7-50 KB depending on parameters); the benefit is that the security
argument is conservative and the design is structurally different from
ML-DSA (Dilithium), which gives the standardised PQ stack TWO families.

NIST standardised SPHINCS+ as SLH-DSA in FIPS 205 (August 2024). The
``pqcrypto`` Python wrapper exposes the reference implementation directly
under module names like ``sphincs_sha2_128f_simple``. The ``f`` variant
optimises for fast signing at the cost of signature size; ``s`` shrinks
the signature at the cost of slower signing.

Penumbra uses SPHINCS+-128f-simple (SHA2 hash family, 128-bit security)
as a *backup* signature family alongside ML-DSA-65: validators may
register a SPHINCS+ public key so that if Dilithium's structured
lattice security argument ever weakens, finality can switch to
SPHINCS+ without a key-ceremony hard fork.

References
----------
- NIST FIPS 205: Stateless Hash-Based Digital Signature Standard.
- Bernstein et al. "SPHINCS+: Submission to NIST PQC round 3" (2020).
"""

from __future__ import annotations

import secrets as _secrets  # only used to derive demo messages, not key material
from dataclasses import dataclass

from pqcrypto.sign.sphincs_sha2_128f_simple import (
    generate_keypair as _sphincs_keypair,
)
from pqcrypto.sign.sphincs_sha2_128f_simple import (
    sign as _sphincs_sign,
)
from pqcrypto.sign.sphincs_sha2_128f_simple import (
    verify as _sphincs_verify,
)

# Dimensions for the demo's size comparison vs ML-DSA-65 (Dilithium-3).
# SPHINCS+-128f-simple is the NIST parameter set with the FAST signing
# regime and 128-bit classical security.
PUBLIC_KEY_BYTES = 32
SECRET_KEY_BYTES = 64
# Signature size is fixed per parameter set; the value below is the
# documented constant for sphincs-sha2-128f-simple.
SIGNATURE_BYTES = 17_088

# For the dashboard tile: ML-DSA-65 reference sizes (NIST FIPS 204).
DILITHIUM3_PUBLIC_KEY_BYTES = 1_952
DILITHIUM3_SIGNATURE_BYTES = 3_309


class SPHINCSError(RuntimeError):
    """Raised for malformed inputs that the verifier rejects."""


@dataclass(frozen=True, slots=True)
class SPHINCSKeypair:
    """SPHINCS+-128f-simple keypair. The secret key is the seed material."""

    public_key: bytes
    secret_key: bytes


def keygen() -> SPHINCSKeypair:
    """Generate a fresh SPHINCS+-128f-simple keypair from the OS CSPRNG."""
    pk, sk = _sphincs_keypair()
    return SPHINCSKeypair(public_key=pk, secret_key=sk)


def sign(secret_key: bytes, message: bytes) -> bytes:
    """Produce a detached SPHINCS+ signature over ``message``.

    pqcrypto's wrapper already exposes a detached (sk, msg) → sig API
    for the SPHINCS+ family. We pass it through verbatim.
    """
    return bytes(_sphincs_sign(secret_key, message))


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Verify a detached SPHINCS+ signature. Returns False on any failure.

    We coerce the result to a Python bool so callers can rely on the
    False branch even when the underlying wrapper raises on malformed
    inputs.
    """
    if len(signature) != SIGNATURE_BYTES:
        return False
    try:
        return bool(_sphincs_verify(public_key, message, signature))
    except Exception:
        return False


def demo() -> dict[str, object]:
    """Sign + verify with SPHINCS+; tamper-test; return size comparison."""
    kp = keygen()
    message = b"penumbra-sphincs-demo:" + _secrets.token_bytes(16)
    sig = sign(kp.secret_key, message)
    honest_ok = verify(kp.public_key, message, sig)
    tampered_msg_ok = verify(kp.public_key, message + b"!", sig)
    bad_sig = bytearray(sig)
    bad_sig[0] ^= 0xFF
    tampered_sig_ok = verify(kp.public_key, message, bytes(bad_sig))
    return {
        "available": True,
        "algorithm": "SPHINCS+-128f-simple (NIST FIPS 205 SLH-DSA)",
        "public_key_bytes": PUBLIC_KEY_BYTES,
        "signature_bytes": SIGNATURE_BYTES,
        "dilithium3_public_key_bytes": DILITHIUM3_PUBLIC_KEY_BYTES,
        "dilithium3_signature_bytes": DILITHIUM3_SIGNATURE_BYTES,
        "size_ratio_sig_sphincs_vs_dilithium": round(
            SIGNATURE_BYTES / DILITHIUM3_SIGNATURE_BYTES, 2
        ),
        "size_ratio_pk_sphincs_vs_dilithium": round(
            PUBLIC_KEY_BYTES / DILITHIUM3_PUBLIC_KEY_BYTES, 4
        ),
        "public_key_short": kp.public_key.hex()[:32],
        "signature_short": sig.hex()[:32],
        "honest_verifies": bool(honest_ok),
        "tampered_message_verifies": bool(tampered_msg_ok),
        "tampered_signature_verifies": bool(tampered_sig_ok),
        "notes": (
            "Hash-based PQ signatures trade signature size for "
            "structural simplicity. Use SPHINCS+ when ML-DSA's "
            "lattice assumption is too narrow."
        ),
    }
