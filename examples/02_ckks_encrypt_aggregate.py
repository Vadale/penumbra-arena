"""CKKS homomorphic encryption — encrypt, aggregate, decrypt.

Concept taught: CKKS lets the *server* sum encrypted vectors and the
*client* (holder of the secret key) recover the plaintext sum. The
server learns nothing about either summand. This is the primitive
that makes "federated aggregation" actually private — the parameter
server never sees individual gradients.

Runs standalone:
    uv run python examples/02_ckks_encrypt_aggregate.py

Backend is whichever HE library is available: OpenFHE (preferred) or
TenSEAL (fallback). Set PENUMBRA_HE_BACKEND=tenseal to force the
fallback. The Protocol is the same either way.
"""

from __future__ import annotations

import numpy as np
from penumbra_crypto.ckks import get_backend


def main() -> None:
    print("=== CKKS encrypt → server-side add → decrypt ===\n")

    # Two client-side plaintexts. Imagine these are two ML clients'
    # gradient updates that they want to aggregate via an honest-but-
    # curious server without revealing them individually.
    alice = np.array([1.5, 2.7, -0.3, 4.0, 8.8], dtype=np.float64)
    bob = np.array([0.5, -1.7, 1.3, 6.0, 1.2], dtype=np.float64)
    expected_sum = alice + bob

    # `get_backend()` reads PENUMBRA_HE_BACKEND env var.
    # Default tries OpenFHE first, falls back to TenSEAL.
    he = get_backend()
    print(f"backend: {type(he).__name__}\n")

    # Client side: encrypt each vector under the same key. In a real
    # FL setting the clients would all share the public key but each
    # would encrypt locally before shipping ciphertext to the server.
    print("client A encrypts:", alice)
    ct_a = he.encrypt(alice)
    print("client B encrypts:", bob)
    ct_b = he.encrypt(bob)

    # Server side: NEVER sees plaintext. Just adds two opaque blobs.
    # In Penumbra's `federated.py` aggregation this is where the
    # parameter server lives.
    print("\nserver-side add (cannot see plaintext)…")
    ct_sum = he.add(ct_a, ct_b)

    # Client side: decrypt the result.
    decrypted = np.asarray(he.decrypt(ct_sum))[: len(alice)]
    print("decrypted sum:", decrypted)
    print("expected sum :", expected_sum)

    # CKKS is *approximate* — there's quantisation noise from the
    # encoding step. We check that the per-slot error is small.
    abs_error = np.abs(decrypted - expected_sum)
    print(f"\nmax per-slot error: {float(abs_error.max()):.2e}")
    print(f"L2 error          : {float(np.linalg.norm(abs_error)):.2e}")

    assert abs_error.max() < 1e-3, "CKKS noise should be well below the 1e-3 floor"
    print("\nOK — CKKS round-trip succeeded under the noise budget.")

    print("\n=== Try this ===")
    print("- Encrypt 50 client vectors and add them all server-side: pure SIMD on the ciphertext.")
    print(
        "- Tamper with the ciphertext bytes before decrypt → garbage out, no crash (no integrity)."
    )
    print("- Switch backend: PENUMBRA_HE_BACKEND=tenseal uv run python examples/02_*.py")
    print("- The CKKS wrapper lives at packages/crypto/penumbra_crypto/ckks.py.")


if __name__ == "__main__":
    main()
