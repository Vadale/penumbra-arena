# penumbra-crypto — the cryptographic primitives

This package is the differentiator. Most multi-agent arenas / RL labs
don't ship a working CKKS, a real DP accountant, a Merkle that fixes
CVE-2012-2459, AND a from-scratch SMPC pedagogical layer in the same
repo. This README is the tour of what's in here, why it's here, and
how to use each piece standalone.

## What you get

| Subsurface | Primitives | Where it ships in Penumbra |
|---|---|---|
| **HE — homomorphic encryption** | CKKS (TenSEAL / OpenFHE auto) + TFHE-LWE (educational) | per-tick encrypted heatmap; FL CKKS-encrypted aggregation |
| **DP — differential privacy** | Laplace mechanism + hard budget + CSPRNG-seeded noise | every release out of the encrypted heatmap; FL DP-SGD pipeline |
| **PQ — post-quantum** | Kyber (ML-KEM-768) KEM, Dilithium (ML-DSA-65) sigs, SPHINCS+ (FIPS 205) hash-based sigs | per-agent move signing; PQ key-exchange demo |
| **BLS aggregate** | BLS12-381 sign + aggregate + fast_aggregate_verify + key-zeroize | chain finality (N validators → 1 × 96-byte sig) |
| **ZK** | Groth16 verifier (pure Python, py_ecc), STARK FRI verifier (educational) | chain match-outcome proofs |
| **VRF** | Schnorr-VRF | PoS leader election |
| **VDF** | Wesolowski | unbiasable randomness |
| **Threshold** | FROST (threshold Schnorr), threshold ECDSA (GG18 educational) | n-of-n co-signature demos |
| **Selective disclosure** | BBS+ (anonymous credentials) | "prove attribute i without revealing the rest" demo |
| **State trees** | Verkle (KZG-based, BLS12-381) | proof-size comparison vs Merkle |
| **Anonymity / mixing** | Loopix mix-net, PSI (OPRF/DH) | metadata-hiding dispatch demo |
| **Defenses** | k-anonymity, ℓ-diversity, padding, request obfuscation, GAN synthetic-trace release, data poisoning | live curves on the dashboard's "defenses" section |
| **Educational SMPC** | Shamir secret sharing, Beaver triples, Pedersen commitments, Schnorr Σ-protocol, Yao garbled circuits, LWE-based TFHE | self-contained pedagogical re-implementations |

## Try the primitives standalone

The fastest way to see what each does is `examples/`:

```sh
uv run python examples/01_dp_budget_walkthrough.py     # DP + hard budget
uv run python examples/02_ckks_encrypt_aggregate.py    # CKKS round-trip
uv run python examples/03_shamir_secret_sharing.py     # (n, t) SS
uv run python examples/05_rdp_dp_sgd_accountant.py     # Rényi DP for DP-SGD
uv run python examples/06_bls_aggregate_finality.py    # BLS N→1 aggregate
```

Each example exercises ONE primitive without booting the dashboard.

## How to use the high-leverage pieces

### CKKS (homomorphic encryption)

```python
from penumbra_crypto.ckks import get_backend
import numpy as np

he = get_backend()  # reads PENUMBRA_HE_BACKEND env var
# Client A and Client B each encrypt their data.
ct_a = he.encrypt(np.array([1.5, 2.7, 4.0]))
ct_b = he.encrypt(np.array([0.5, -1.7, 6.0]))
# Server adds the two ciphertexts. It cannot decrypt either.
ct_sum = he.add(ct_a, ct_b)
# Anyone with the secret key can decrypt the sum.
print(he.decrypt(ct_sum))  # ≈ [2.0, 1.0, 10.0]
```

Switch backends via `PENUMBRA_HE_BACKEND=tenseal` or `=openfhe`. The
Protocol is the same; OpenFHE is preferred on Linux x86_64, TenSEAL
is the fallback (and the only path on macOS where OpenFHE-Python
doesn't ship arm64 wheels).

**Gotcha**: CKKS is *approximate*. Per-slot error is ~1e-9 after one
add, larger after multiplications (which we don't ship in this lab —
the heatmap aggregation only adds). If you ship a multiplication, call
`.rescale()` to renormalise the scaling factor; we don't because we
don't need it.

### Differential privacy with a hard budget

```python
from penumbra_crypto.dp import DPMechanism, PrivacyBudget, BudgetExceededError

budget = PrivacyBudget(epsilon=1.0)  # ε_total = 1.0 ever
dp = DPMechanism(budget=budget)      # auto-CSPRNG-seeded

# Each release deducts from the budget BEFORE drawing noise.
try:
    noised = dp.laplace(value=12345.67, sensitivity=1.0, epsilon=0.1)
except BudgetExceededError:
    # The mechanism refuses to release further; treat as "DP off".
    ...
```

The CSPRNG seed (`secrets.token_bytes`) is the difference between
"toy DP" and "DP an adversary can't subtract noise from by guessing
the seed". `numpy.random.default_rng()` without an explicit
cryptographic seed does not give you adversarial DP.

### Rényi DP for DP-SGD (training-time budget)

```python
from penumbra_learning.federated_dp import RDPAccountant

sigma = 1.1   # noise multiplier
q = 0.01      # subsampling rate (batch / dataset)

acc = RDPAccountant()  # 118-order grid (denser than legacy 12)
for _ in range(1000):
    acc.step(noise_multiplier=sigma, sample_rate=q)
print(acc.epsilon(target_delta=1e-5))  # tight (ε, δ) bound
```

The dense order grid yields a tighter ε than the legacy ~12-order
Opacus-style grid; `examples/05_rdp_dp_sgd_accountant.py` shows the
numeric comparison.

### BLS aggregate signatures

```python
from penumbra_crypto.bls import keygen, sign, aggregate_signatures, fast_aggregate_verify

validators = [keygen() for _ in range(5)]
block_hash = b"block-deadbeef"
sigs = [sign(v.secret_key, block_hash) for v in validators]
agg = aggregate_signatures(sigs)  # 1 × 96 bytes regardless of N

ok = fast_aggregate_verify([v.public_key for v in validators], block_hash, agg)
assert ok
```

**Defense note**: `aggregate_signatures` is vulnerable to the
rogue-key attack if any pubkey hasn't proven knowledge of its secret
key. Penumbra's chain calls `verify_possession()` at validator
registration to close this; if you reuse this code, do the same.

### Shamir secret sharing

```python
from penumbra_crypto.educational import shamir

shares = shamir.split(secret=0xCAFEBABE, n=5, t=3)
recovered = shamir.reconstruct(shares[:3])  # any 3 of 5
assert recovered == 0xCAFEBABE
```

This is pure-Python pedagogical code — ~95 LOC. Every step (polynomial
construction, Lagrange interpolation, field arithmetic) is visible in
source. For production use, see `nacl` / Vault Transit / Halo.

## Security properties — what the audit closed

The 6 LOW + 4 MED findings from the security audit (see
[`SECURITY_AUDIT.md`](../../SECURITY_AUDIT.md)) are all closed as of
v1.0:

- **Merkle CVE-2012-2459**: level-tagged internal hashes + fixed
  zero-leaf pad. See `examples/04_merkle_cve_2012_2459.py`.
- **DP-SGD per-example clipping**: `torch.func.vmap(grad(...))` —
  not aggregated-then-clipped (which loses the per-example sensitivity
  bound Abadi 2016 needs).
- **Poisson subsampling** (not random sampling with replacement) for
  the DP-SGD step — matches the SGM RDP analysis.
- **CSPRNG-seeded DP noise**: `secrets.token_bytes` → PCG64 seed.
- **Groth16 G2 subgroup membership check** on public inputs.
- **Constant-time `hmac.compare_digest`** in VRF + timing-sidechannel
  paths (was `==` on bytes).
- **Atomic `tmp+rename`** for secret-key / DP-budget persistence.
- **Key zeroization** where secret keys leave scope (BLS).
- **Densified RDP order grid** (118 orders, was 12) for tighter ε.
- **Stake-weighted finality threshold** option (was vote-weighted).

The audit's verdict is `SAFE-FOR-RESEARCH + SAFE-FOR-DEMO`. NOT
production-grade — see the audit document for what's deferred for
production hardening.

## Extracting this package as a spin-off

`penumbra_crypto/educational/` is the cleanest extraction target — it
has zero dependencies on the rest of Penumbra. The plan (parked) is
to publish it as `penumbra-educational-crypto` on PyPI for university
adoption.

If you want to do this:
1. Copy `packages/crypto/penumbra_crypto/educational/` to a new repo.
2. Lift the imports — `shamir.field_modulus()` etc. are already
   self-contained.
3. Write a top-level `__init__.py` exposing `shamir`, `beaver`,
   `pedersen`, `schnorr`, `tfhe_boolean`, `yao`.
4. Add a `pyproject.toml` declaring `requires-python = ">=3.12"` and
   `numpy>=2.0`.
5. Publish.

Expected work: 2-3 days. The hardest part is writing the README for
the new repo (which can largely lift from this one's "Try the
primitives" section).

## Original (concept-taught) primer

Penumbra's cryptographic primitives. Densest single learning module
in the project; each file maps to one concept and ships with a
property-based test.

| File | Concept |
|---|---|
| `ckks.py` | approximate HE via TenSEAL/OpenFHE; SIMD pack |
| `dp.py` | Laplace mechanism + budget accountant |
| `pq.py` | post-quantum primitives (Kyber + Dilithium) |
| `bls.py` | BLS12-381 aggregate sigs (validator finality) |
| `vrf.py` | Schnorr-VRF leader election |
| `vdf.py` | Wesolowski VDF (T squarings, fast verify) |
| `snark.py` | Groth16 verifier (pairing-based) |
| `stark.py` | FRI-STARK verifier (transparent setup) |
| `frost.py` | threshold Schnorr signatures |
| `sphincs.py` | hash-based PQ signatures |
| `verkle.py` | KZG-opening-based state tree |
| `bbs_plus.py` | anonymous credentials with selective disclosure |
| `threshold_ecdsa.py` | n-of-n ECDSA (educational GG18) |
| `psi.py` | private set intersection (OPRF/DH) |
| `mix_net.py` | Loopix-style onion routing |
| `educational/shamir.py` | (n, t) Shamir secret sharing over a prime field |
| `educational/beaver.py` | Beaver multiplication triples for SMPC |
| `educational/pedersen.py` | Pedersen commitments (binding + hiding) |
| `educational/schnorr.py` | Schnorr Σ-protocol + Fiat-Shamir NIZK |
| `educational/tfhe_boolean.py` | LWE-based bit-gate TFHE (educational) |
| `educational/yao.py` | Yao garbled circuits + millionaires comparator |
| `defenses/k_anonymity.py` | suppression-based k-anonymity |
| `defenses/l_diversity.py` | k-anon + distinct sensitive values |
| `defenses/padding.py` | message padding + Poisson cover traffic |
| `defenses/gan_defenses.py` | synthetic-trace release |
| `defenses/data_poisoning.py` | decoy injection |
| `defenses/request_obfuscation.py` | Bonferroni + dummy DP queries |

## Micro-experiments per file

Each concept has a runnable `if __name__ == "__main__"` block; run
`uv run python -m penumbra_crypto.<file>` to see it in action. The
`examples/` directory holds the curated entry-points for the most
common primitives.
