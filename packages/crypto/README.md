# penumbra-crypto

Penumbra's cryptographic primitives.

## Concept taught

This is the densest single learning module in Penumbra. Each file maps to
one concept:

- `ckks.py` — CKKS approximate-arithmetic homomorphic encryption.
- `tfhe.py` — TFHE encrypted boolean/comparison operations.
- `dp.py` — Laplace-mechanism differential privacy with an accountant.
- `pq.py` — post-quantum KEM (Kyber768) and signatures (Dilithium3).
- `bls.py` — BLS aggregate signatures with rogue-key defence.
- `vrf.py` — Schnorr-VRF for unbiased leader election.
- `vdf.py` — Wesolowski VDF for unbiasable randomness.
- `snark.py` — Groth16 zk-SNARK verifier.
- `educational/` — from-scratch Shamir, Beaver, Pedersen, Schnorr —
  pedagogical implementations exercised by tests only, never on the
  hot path.

Backend toggle: `PENUMBRA_HE_BACKEND={openfhe,tenseal}` selects the CKKS
adapter at startup. OpenFHE is the default (more precise) but TenSEAL
is auto-selected if the OpenFHE import fails.
