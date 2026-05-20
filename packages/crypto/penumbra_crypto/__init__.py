"""Penumbra cryptography.

Concept taught: an integrated tour of practical, production-flavoured
cryptography. CKKS / TFHE for encrypted aggregates, differential privacy
for noisy releases, post-quantum signatures, BLS aggregate signatures,
VRF for unbiased leader election, VDF for unbiasable randomness, a
Groth16 verifier for zk-SNARKs, and a pedagogical re-implementation of
SMPC + ZK building blocks from scratch.

Backend selection:
  PENUMBRA_HE_BACKEND=tenseal   (default on Apple Silicon)
  PENUMBRA_HE_BACKEND=openfhe   (default on Linux x86_64 if available)

If the requested backend can't be imported, we fall back to whichever
*can*. The HEBackend protocol guarantees a uniform interface either way.
"""

from penumbra_crypto.ckks import HEBackend, get_backend

__all__ = ["HEBackend", "get_backend"]
