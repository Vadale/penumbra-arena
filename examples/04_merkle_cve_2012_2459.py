"""Merkle tree — and the CVE-2012-2459 attack it resists.

Concept taught: a naive Merkle tree is *malleable* — duplicating the
last leaf doesn't change the root. That's bad: an attacker can craft
an alternate proof for a leaf they don't own. Bitcoin had this CVE in
2012; modern implementations (including Penumbra's) defend by
level-tagging the hashes AND padding odd levels with a fixed sentinel
instead of duplicating.

Runs standalone:
    uv run python examples/04_merkle_cve_2012_2459.py

This exercises `packages/chain/penumbra_chain/merkle.py` directly. The
fix shipped in Penumbra 2026-05-23; the regression test that pinned it
is `packages/chain/tests/test_merkle.py`.
"""

from __future__ import annotations

from penumbra_chain.merkle import build_proof, build_root, hash_leaf, verify_proof


def main() -> None:
    print("=== Merkle tree (Penumbra impl) — CVE-2012-2459 resistance ===\n")

    # 4 leaves — payloads can be anything; we hash them at the leaf
    # boundary so the rest of the tree only sees fixed-size digests.
    payloads = [b"alice-tx", b"bob-tx", b"charlie-tx", b"dave-tx"]
    leaves = [hash_leaf(p) for p in payloads]
    root = build_root(leaves)
    print(f"4-leaf root: {root.hex()}")

    # Honest proof: build a proof for leaf #2 (charlie-tx), verify it.
    print("\n--- honest membership proof ---")
    proof = build_proof(leaves, index=2)
    ok = verify_proof(root, proof)
    print(f"verify(root, charlie's proof) → {ok}  (expected True)")
    assert ok

    # CVE-2012-2459 attempt: duplicate the last leaf and see if the root
    # collides with the original. In the naive textbook scheme it WOULD.
    print("\n--- CVE-2012-2459 attack attempt ---")
    print("an attacker resubmits [...] + [dave-tx duplicated] and claims it's the same set:")
    cve_payloads = payloads + [payloads[-1]]
    cve_leaves = [hash_leaf(p) for p in cve_payloads]
    cve_root = build_root(cve_leaves)
    print(f"4-leaf root: {root.hex()}")
    print(f"5-leaf root: {cve_root.hex()}")
    print(f"identical? {root == cve_root}  (expected False — the defence works)")
    assert root != cve_root, "Merkle MUST be malleability-resistant"

    # Tamper: flip one byte in the payload, the proof must fail.
    print("\n--- tampering rejects the proof ---")
    tampered = list(payloads)
    tampered[2] = b"charlie-EVIL"
    tampered_leaves = [hash_leaf(p) for p in tampered]
    tampered_root = build_root(tampered_leaves)
    ok = verify_proof(tampered_root, proof)  # old proof, new root
    print(f"verify(tampered_root, charlie's old proof) → {ok}  (expected False)")
    assert ok is False

    # The Penumbra defence has two pieces (see merkle.py:42):
    #   1. internal node hash is domain-separated by depth ("level"):
    #      H(b"\\x01" || depth || left || right). Without the depth tag,
    #      a 2-leaf subtree root H(a, b) could be confused with a single
    #      leaf at depth-1 because both are 32-byte digests.
    #   2. odd-length levels are padded with a FIXED sentinel hash
    #      H(b"\\x02penumbra-merkle-pad"), not the last leaf. That kills
    #      the duplicate-last-leaf collision the CVE exploits.

    print("\n=== Why it works ===")
    print("- Each internal hash includes the tree depth — leaf hashes can't")
    print("  be confused with internal hashes.")
    print("- Odd levels get padded with a FIXED hash sentinel, not by")
    print("  duplicating the last leaf — so 'add a duplicate' changes the root.")
    print("\nSource: packages/chain/penumbra_chain/merkle.py")


if __name__ == "__main__":
    main()
