#!/usr/bin/env bash
# Build the `legal_path.circom` Groth16 circuit + generate a sample
# proof for the input `inputs/legal_path_sample.json`.
#
# This is the "semantic" Penumbra Groth16 demo: it proves "I know
# an intermediate node such that (start → mid) and (mid → goal) are
# both edges in the published 4×4 arena adjacency bitmap". Real
# zero-knowledge over a real graph walk — not the multiplier
# hello-world.
#
# Idempotent — re-running won't redo expensive steps if their outputs
# exist.

set -euo pipefail

cd "$(dirname "$0")"

# Reuse the local powers-of-tau ceremony from setup.sh.
if [[ ! -f powers_of_tau_final.ptau ]]; then
    echo "→ powers_of_tau_final.ptau missing — generate it via setup.sh first"
    exit 1
fi

# Install circomlib if needed (used for IsEqual).
if [[ ! -d node_modules/circomlib ]]; then
    echo "→ installing circomlib..."
    npm install --silent circomlib
fi

# Compile.
if [[ ! -f build/legal_path.r1cs ]]; then
    echo "→ compiling legal_path.circom..."
    circom legal_path.circom --r1cs --wasm --sym -o build/ -l node_modules
fi

# Groth16 setup.
if [[ ! -f build/legal_path.zkey ]]; then
    echo "→ Groth16 setup..."
    snarkjs groth16 setup \
        build/legal_path.r1cs \
        powers_of_tau_final.ptau \
        build/legal_path.zkey
fi

if [[ ! -f artifacts/legal_path_vk.json ]]; then
    echo "→ exporting verifying key..."
    snarkjs zkey export verificationkey \
        build/legal_path.zkey \
        artifacts/legal_path_vk.json
fi

# Witness + proof.
echo "→ generating witness from inputs/legal_path_sample.json..."
node build/legal_path_js/generate_witness.js \
    build/legal_path_js/legal_path.wasm \
    inputs/legal_path_sample.json \
    build/legal_path_witness.wtns

echo "→ generating proof..."
snarkjs groth16 prove \
    build/legal_path.zkey \
    build/legal_path_witness.wtns \
    artifacts/legal_path_proof.json \
    artifacts/legal_path_public.json

echo "→ snarkjs self-verify..."
snarkjs groth16 verify \
    artifacts/legal_path_vk.json \
    artifacts/legal_path_public.json \
    artifacts/legal_path_proof.json

echo ""
echo "done. artifacts in circuits/artifacts/legal_path_*.json"
echo "next: uv run pytest packages/crypto/tests/test_circom_legal_path.py"
