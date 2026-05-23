"""Merkle-tree hardening tests.

Concept taught: the Bitcoin Merkle construction is malleable under
leaf duplication (CVE-2012-2459) — `build_root([a, b, c])` and
`build_root([a, b, c, c])` collide because the odd-leaf handler
duplicates the last node. Penumbra defends with two changes:

1. internal-node hashes are tagged with the level (height above
   the leaf layer), so a child cannot be mistaken for a parent;
2. odd-length levels are padded with a fixed `_PADDING_NODE`
   sentinel instead of by duplicating the last leaf.

The tests below pin both the inequality and a known-good root, so
any accidental change to the hashing scheme is caught immediately.
"""

from __future__ import annotations

from penumbra_chain import merkle


def test_merkle_resists_leaf_duplication_malleability() -> None:
    """CVE-2012-2459: duplicating the last leaf must change the root."""
    base = merkle.build_root([b"a", b"b", b"c"])
    duplicated = merkle.build_root([b"a", b"b", b"c", b"c"])
    assert base != duplicated, (
        "build_root([a, b, c]) collides with build_root([a, b, c, c]) — "
        "leaf-duplication malleability has reappeared"
    )


def test_merkle_resists_duplication_at_arbitrary_odd_length() -> None:
    """Same property must hold for longer odd-length lists, not just 3."""
    leaves_odd = [f"leaf-{i}".encode() for i in range(5)]
    leaves_dup = [*leaves_odd, leaves_odd[-1]]
    assert merkle.build_root(leaves_odd) != merkle.build_root(leaves_dup)

    leaves_odd_seven = [f"leaf-{i}".encode() for i in range(7)]
    leaves_dup_seven = [*leaves_odd_seven, leaves_odd_seven[-1]]
    assert merkle.build_root(leaves_odd_seven) != merkle.build_root(leaves_dup_seven)


def test_merkle_root_stable_under_known_input() -> None:
    """Regression: pin the root for a fixed input.

    If this test fails the hashing scheme has changed and any
    persisted chain state is invalidated. Update the expected hex
    only when the hashing change is intentional and reviewed.
    """
    leaves = [b"leaf-0", b"leaf-1", b"leaf-2", b"leaf-3", b"leaf-4"]
    expected = bytes.fromhex("3dcf3b63e75872fdf78bf6b42b6453ce7f2a9ad5c7cb319293274e1755dd362a")
    assert merkle.build_root(leaves) == expected
