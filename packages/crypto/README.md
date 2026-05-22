# penumbra-crypto

Penumbra's cryptographic primitives. Densest single learning module
in the project; each file maps to one concept and ships with a
property-based test.

## Concept taught

| File | What it teaches |
|---|---|
| `ckks.py` | CKKS approximate-arithmetic homomorphic encryption (Cheon-Kim-Kim-Song 2017). SIMD-packed vectors; `rescale` after every multiplication keeps the modulus chain healthy. Backend toggle `PENUMBRA_HE_BACKEND={tenseal,openfhe,auto}`; default tenseal on Apple Silicon, openfhe on Linux x86_64. |
| `dp.py` | Laplace-mechanism differential privacy with a **mandatory** `PrivacyBudget` accountant. Deduct from ε/δ on every release; the mechanism never noises without first checking budget. Live in the encrypted-heatmap path; remaining ε visible at `/dp/budget`. |
| `pq.py` | NIST-finalised post-quantum primitives: ML-KEM-768 (Kyber, FIPS 203) for key encapsulation, ML-DSA-65 (Dilithium, FIPS 204) for signatures. Each agent gets a Dilithium keypair at boot; per-tick moves are signed and verified. |
| `bls.py` | BLS aggregate signatures on BLS12-381 via py_ecc. Includes proof-of-possession defence against rogue-key attacks. N validator sigs collapse into one 96-byte aggregate verified by one pairing equation. |
| `vrf.py` | Schnorr-VRF over the RFC 3526 MODP-14 Schnorr group. Leader election: every validator computes β_i = VRF(sk_i, prev_hash); lowest β wins. No grinding, no prediction. |
| `vdf.py` | Wesolowski VDF — sequential repeated-squaring in a Schnorr group, with a short Fiat-Shamir prime proof. The "wait T squarings then publish y + π" pattern unbiasable randomness consumes. |
| `snark.py` | Groth16 zk-SNARK *verifier* (one pairing equation, constant time). Loads snarkjs-format `vk.json` + `proof.json` + `public.json` straight in. Real circom-generated artifacts in `circuits/artifacts/` are verified by `tests/test_circom_integration.py`. |
| `crypto_persistence.py` | TenSEAL context (re-)serialisation + DP-budget JSON round-trip. CKKS keys + DP ε spent survive across restarts via `state/snapshots/<name>/crypto/`. |
| `educational/shamir.py` | (k,n) Shamir Secret Sharing from scratch. Lagrange interpolation in a finite field. |
| `educational/beaver.py` | Beaver multiplication triples — the canonical primitive for SMPC arithmetic on private inputs. |
| `educational/pedersen.py` | Pedersen commitments — hiding + binding + additive homomorphism. |
| `educational/schnorr.py` | Schnorr Σ-protocol with Fiat-Shamir; the simplest non-trivial ZK proof of knowledge. |
| `educational/tfhe_boolean.py` | LWE-based homomorphic XOR/NOT/NAND/AND/OR from scratch. ~150 LOC. Demo: encrypted faction overlap. No bootstrapping (documented caveat); for production, swap for a Concrete-Python compiled circuit. |

## Dashboard panels exposing these primitives

| Primitive | Tile | Endpoint |
|---|---|---|
| CKKS | "CKKS" | `/crypto/ckks/compare` |
| DP (Laplace) | "DP δ" | `/dp/compare` |
| Kyber (ML-KEM-768) | "Kyber" | `/crypto/kyber/demo` |
| Dilithium (ML-DSA-65) | "Dilithium" | `/crypto/dilithium/inspect/{id}` |
| BLS aggregate | "BLS agg" | `/chain/bls/{hash}` |
| VRF leader | "VRF leader" | `/chain/vrf-leader` |
| VDF (Wesolowski) | "VDF" | `/crypto/vdf/demo` |
| Groth16 zk-SNARK | "ZK proof" | `/crypto/zk/legal-path` |
| Shamir SSS | "Shamir" | `/crypto/shamir/demo` |
| TFHE (LWE) | "TFHE" | `/crypto/tfhe/demo` |

## Real-circuit Groth16 demo

Outside this package — `circuits/` at the repo root — circom +
snarkjs generate a `multiplier.circom` proof and our Python
verifier accepts it:

```sh
cd circuits && bash setup.sh    # ~30 s, idempotent
uv run pytest packages/crypto/tests/test_circom_integration.py
```

## Crypto rules (enforced by `crypto-auditor`)

- **Never** use `numpy.random` or `random` for key material.
  `secrets.token_bytes` only.
- Constant-time comparisons via `hmac.compare_digest`. Never `==`.
- CKKS: rescale after every `*` unless the multiplicative depth has
  been explicitly budgeted.
- Nonces from `secrets.token_bytes`; never reuse a Schnorr nonce.
- Any change to this package or to `chain/` or `attacker/` must
  pass `crypto-auditor` review before merging.

## Micro-experiments

1. **Watch the CKKS modulus chain shrink**:
   ```python
   from penumbra_crypto.ckks import TenSEALBackend
   import numpy as np
   b = TenSEALBackend()
   v = b.encrypt(np.array([1.0, 2.0, 3.0]))
   v2 = b.multiply(v, v)
   v3 = b.multiply(v2, v)  # depth budget gets tight here
   ```
2. **Verify a real circom proof through our verifier**:
   ```python
   import json
   from pathlib import Path
   from penumbra_crypto.snark import load_proof, load_verifying_key, verify
   art = Path("circuits/artifacts")
   vk = load_verifying_key(json.loads((art / "vk.json").read_text()))
   pf = load_proof(json.loads((art / "proof.json").read_text()))
   public = [int(s) for s in json.loads((art / "public.json").read_text())]
   assert verify(vk, pf, public)
   ```
3. **Exhaust a DP budget** and watch the accountant refuse:
   ```python
   from penumbra_crypto.dp import PrivacyBudget, DPMechanism
   budget = PrivacyBudget(epsilon=1.0)
   mech = DPMechanism(budget)
   # ... 25 noised releases at ε=0.05 each spends the budget
   ```
