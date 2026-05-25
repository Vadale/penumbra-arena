"""BLS aggregate signatures — N signers, ONE 96-byte signature.

Concept taught: BLS12-381 signatures are points on an elliptic curve;
the group operation is addition. Adding N validators' signatures
yields one point that verifies against the *combined* public keys via
a pairing equation. The verifier's cost is constant in N. This is
exactly what makes proof-of-stake finality cheap: N validators sign
the block hash, the chain stores one 96-byte aggregate, anyone can
verify the block is endorsed by the >2/3 quorum.

Runs standalone:
    uv run python examples/06_bls_aggregate_finality.py

Exercises `packages/crypto/penumbra_crypto/bls.py`. The chain's block
finality loop in `packages/chain/penumbra_chain/node.py` calls this
exact path.
"""

from __future__ import annotations

from penumbra_crypto.bls import aggregate_signatures, fast_aggregate_verify, keygen, sign


def main() -> None:
    print("=== BLS aggregate signatures — N validators, 1 sig ===\n")

    # Pretend we have 5 validators in the chain's active set.
    N = 5
    validators = [keygen() for _ in range(N)]
    print(f"generated {N} BLS keypairs (each pk is 48 bytes)")
    for i, kp in enumerate(validators):
        print(f"  validator {i}: pk = {kp.public_key.hex()[:40]}…")

    # The "block hash" being signed. In Penumbra this is the actual
    # SHA-256 of the block header.
    block_hash = b"block-hash-deadbeef-cafe-1234"

    # Each validator signs locally. The signing parties don't talk to
    # each other — that's the key property.
    sigs = [sign(v.secret_key, block_hash) for v in validators]
    print("\nN sigs (each 96 bytes G2 point):")
    for i, s in enumerate(sigs):
        print(f"  sig {i}: {s.hex()[:48]}…")

    # The chain combines them into ONE 96-byte aggregate. The validators
    # could be offline by the time this runs — only the bytes matter.
    agg = aggregate_signatures(sigs)
    print(f"\naggregate (1 × 96 bytes): {agg.hex()[:48]}…")
    print(f"chain storage: N=5 → 1 → saves {(N - 1) * 96} bytes per block")
    print(f"               N=100 → 1 → saves {(100 - 1) * 96} bytes per block")

    # Verify the aggregate against ALL pubkeys + same message. This is
    # the chain's `fast_aggregate_verify` call.
    print("\n--- verify aggregate ---")
    pks = [v.public_key for v in validators]
    ok = fast_aggregate_verify(pks, block_hash, agg)
    print(f"verify(pks, block_hash, agg) → {ok}  (expected True)")
    assert ok

    # Tamper test #1: change the block hash. Should reject.
    print("\n--- tamper: change block hash ---")
    bad_hash = b"block-hash-EVIL-tampered-1234"
    ok = fast_aggregate_verify(pks, bad_hash, agg)
    print(f"verify(pks, BAD_HASH, agg) → {ok}  (expected False)")
    assert ok is False

    # Tamper test #2: drop one signer from the pks. Should reject.
    # (We aggregated N sigs but claim only N-1 pks — pairing equation fails.)
    print("\n--- tamper: claim wrong validator set ---")
    ok = fast_aggregate_verify(pks[:-1], block_hash, agg)
    print(f"verify(pks[:-1], block_hash, agg) → {ok}  (expected False)")
    assert ok is False

    print("\n=== What this gives the chain ===")
    print("- Block storage: 1 sig, not N (huge for large validator sets).")
    print("- Verification: constant time in N (one pairing equation).")
    print("- Threshold finality: aggregate any t-of-N → still one 96-byte point.")
    print("- BUT: every validator must prove possession of their secret first,")
    print("  otherwise a rogue-key attack lets one party forge any aggregate.")
    print("  Penumbra calls `verify_possession()` at validator-set registration.")
    print("\nSource: packages/crypto/penumbra_crypto/bls.py")


if __name__ == "__main__":
    main()
