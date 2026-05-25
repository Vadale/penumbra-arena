# examples/

Standalone scripts that exercise **one Penumbra primitive at a time**,
without booting the full runtime (no FastAPI, no dashboard, no
simulation loop). Each is ~100-200 LOC, self-contained, and runs via:

```sh
uv run python examples/<NAME>.py
```

These exist for two audiences:

1. **Visitors** who want to see "what's in this repo" without committing
   to `make demo`. Pick a topic, run the script, read the source.
2. **Spin-off authors** who want to fork a focused part of Penumbra
   (see `CHANGELOG.md` v1.0 entry). Each script is a working snippet
   of how the standalone library should look once extracted from the
   monorepo.

## The 6 examples

| # | File | What you learn | Source it exercises |
|---|---|---|---|
| 01 | `01_dp_budget_walkthrough.py` | Laplace DP + hard budget that *refuses* over-the-line releases | `packages/crypto/penumbra_crypto/dp.py` |
| 02 | `02_ckks_encrypt_aggregate.py` | CKKS homomorphic add — server sums ciphertexts, learns nothing | `packages/crypto/penumbra_crypto/ckks.py` |
| 03 | `03_shamir_secret_sharing.py` | (n, t) Shamir SS via Lagrange interpolation over a prime field | `packages/crypto/penumbra_crypto/educational/shamir.py` |
| 04 | `04_merkle_cve_2012_2459.py` | Merkle malleability attack and the level-tagged-hash fix | `packages/chain/penumbra_chain/merkle.py` |
| 05 | `05_rdp_dp_sgd_accountant.py` | Rényi DP accountant for DP-SGD — dense vs sparse α grid | `packages/learning/penumbra_learning/federated_dp.py` |
| 06 | `06_bls_aggregate_finality.py` | BLS aggregate sigs — N validators, 1 × 96-byte sig | `packages/crypto/penumbra_crypto/bls.py` |

## Running all of them

```sh
for f in examples/*.py; do
  echo "=== $f ==="
  uv run python "$f" || echo "  ↑ failed"
  echo
done
```

All 6 should print their walkthrough and exit 0 on a fresh `uv sync`.

## How they relate to the spin-off candidates

- Examples 04 + 06 are the core of **`penumbra-chain-sim`** (the top
  spin-off candidate; see `CHANGELOG.md` v1.0 entry). The chain
  package is 95 % reusable; these examples show its standalone shape.
- Example 03 is the seed of **`penumbra-educational-crypto`** — a
  pip-installable library of from-scratch SMPC primitives. The other
  primitives in `packages/crypto/penumbra_crypto/educational/`
  (Beaver, Pedersen, Schnorr, TFHE-LWE, Yao) follow the same pattern.
- Examples 01 + 05 are the privacy-engineering core; a future
  `penumbra-stats-lab` would build a CSV-upload UI on top of them.

## What examples don't cover

- The **simulation loop** (`packages/core/`) — only meaningful inside
  the full runtime; not extractable standalone.
- The **dashboard** — visual; if you want to see it, use `make demo`.
- The **operator cyber-range mode** — pulls in too much state to be
  a 100-LOC script.

For the integrated experience, run `make demo` and click around.
