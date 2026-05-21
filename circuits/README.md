# circuits

Real Groth16 circuits compiled with **circom** + **snarkjs**.
Penumbra's pure-Python verifier (`packages/crypto/penumbra_crypto/snark.py`)
loads the resulting `vk.json` + `proof.json` + `public.json` and checks
the pairing equation against them — no circom toolchain required at
verify time.

## Concept taught

The Groth16 verifier is constant-time, but generating a Groth16 *proof*
requires a complete pipeline:

1. **Circuit**: `multiplier.circom` declares a Rank-1 Constraint System
   (R1CS) for "I know a, b such that a · b = c". `a` and `b` are
   private witnesses; `c` is the public output.
2. **Powers of Tau** (phase 1): a *trusted setup* over the BN128 curve.
   Real ceremonies involve dozens of participants so the toxic-waste
   `tau` is uniformly random in everyone's view. We run a local
   single-party ceremony here for the demo — pedagogical, **not**
   production-safe.
3. **Groth16 setup** (phase 2): compiles the R1CS + ptau into a
   proving key (`zkey`) and a verifying key (`vk.json`).
4. **Witness generation**: feed inputs to the wasm interpreter to
   produce `witness.wtns`.
5. **Proof**: `snarkjs groth16 prove` → `proof.json` (three group
   elements) + `public.json` (the public inputs).
6. **Verify**: any party with `vk.json`, `proof.json`, `public.json`
   evaluates the pairing equation. Penumbra's Python verifier does
   this in `verify(vk, proof, public_inputs)` — one pairing eq,
   regardless of how big the underlying circuit was.

## Quickstart

```sh
# Prerequisites (one-time, ~30 s install):
# - circom 2.2+  (binary from iden3 releases — works under Apple Silicon)
# - snarkjs 0.7+ (npm install -g snarkjs)
# - node        (already on the Mac for the frontend)

cd circuits
bash setup.sh    # ~30 s on M4; idempotent
```

This produces:
- `build/` — circuit compilation outputs (~70 KB, gitignored)
- `powers_of_tau_final.ptau` — 4.8 MB ceremony file (gitignored,
  regenerable in ~10 s)
- `artifacts/{vk,proof,public}.json` — committed, used by the test

## What gets verified

Inputs: `{"a": 3, "b": 5}` (`inputs/sample.json`).
Public output: `15`. Public input list passed to the verifier: `[15]`.

`packages/crypto/tests/test_circom_integration.py` loads the
artifacts and asserts:
- The verifier accepts the legitimate proof.
- The verifier rejects when the public input is tampered (claim 16).
- The verifier rejects on wrong public-input count (empty list, two
  values).

## Generating proofs for other inputs

Edit `inputs/sample.json`, re-run the witness + prove steps:

```sh
node build/multiplier_js/generate_witness.js \
    build/multiplier_js/multiplier.wasm \
    inputs/sample.json \
    build/witness.wtns
snarkjs groth16 prove \
    build/multiplier.zkey \
    build/witness.wtns \
    artifacts/proof.json \
    artifacts/public.json
```

The setup (ptau + zkey + vk.json) is reusable across all inputs to
this circuit — only witness + proof regenerate.
