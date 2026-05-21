#!/usr/bin/env bash
# One-shot Groth16 ceremony + proof generation for the multiplier circuit.
#
# Idempotent: re-running won't redo expensive steps if their outputs exist.
#
# Outputs (all under circuits/):
#   build/multiplier.r1cs           <- compiled constraints
#   build/multiplier_js/multiplier.wasm  <- witness generator
#   build/multiplier.zkey           <- proving + verifying key bundle
#   artifacts/vk.json               <- exported verifying key (snarkjs JSON)
#   artifacts/proof.json + public.json <- a sample proof on inputs/sample.json
#
# Pre-reqs:
#   - circom    >= 2.2 (we use a Mach-O arm64 binary from iden3 releases)
#   - snarkjs   >= 0.7 via npm -g
#
# The Powers-of-Tau ceremony is generated locally because the upstream
# Hermez S3 mirror is unreliable. A locally-generated ptau is fine for
# this educational demo; for production you'd use a public ceremony
# transcript so no single party knows the toxic waste.
#
# Usage:
#   cd circuits && bash setup.sh

set -euo pipefail

cd "$(dirname "$0")"

# ── Powers of Tau (local ceremony, 2^12 size — overkill for our 1-
#     constraint circuit but reusable for larger ones up to ~4 K gates).
if [[ ! -f powers_of_tau_final.ptau ]]; then
    echo "→ phase 1: powers-of-tau (BN128, 2^12)..."
    snarkjs powersoftau new bn128 12 build/pot12_0000.ptau
    snarkjs powersoftau contribute \
        build/pot12_0000.ptau \
        build/pot12_0001.ptau \
        --name="penumbra-local-contrib" \
        -e="penumbra-$(date +%s)"
    echo "→ phase 2 prepare..."
    snarkjs powersoftau prepare phase2 \
        build/pot12_0001.ptau \
        powers_of_tau_final.ptau
    rm -f build/pot12_0000.ptau build/pot12_0001.ptau
fi

# ── circuit compile ────────────────────────────────────────────────
if [[ ! -f build/multiplier.r1cs ]]; then
    echo "→ compiling circuit..."
    circom multiplier.circom --r1cs --wasm --sym -o build/
fi

# ── Groth16 setup + vk export ──────────────────────────────────────
if [[ ! -f build/multiplier.zkey ]]; then
    echo "→ Groth16 setup..."
    snarkjs groth16 setup \
        build/multiplier.r1cs \
        powers_of_tau_final.ptau \
        build/multiplier.zkey
fi

if [[ ! -f artifacts/vk.json ]]; then
    echo "→ exporting verifying key..."
    snarkjs zkey export verificationkey build/multiplier.zkey artifacts/vk.json
fi

# ── proof generation against inputs/sample.json ────────────────────
echo "→ generating witness from inputs/sample.json..."
node build/multiplier_js/generate_witness.js \
    build/multiplier_js/multiplier.wasm \
    inputs/sample.json \
    build/witness.wtns

echo "→ generating proof..."
snarkjs groth16 prove \
    build/multiplier.zkey \
    build/witness.wtns \
    artifacts/proof.json \
    artifacts/public.json

echo "→ snarkjs self-verify..."
snarkjs groth16 verify artifacts/vk.json artifacts/public.json artifacts/proof.json

echo ""
echo "done. artifacts in circuits/artifacts/{vk,proof,public}.json"
echo "next: uv run pytest packages/crypto/tests/test_circom_integration.py"
