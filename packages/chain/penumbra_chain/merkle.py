"""SHA-256 Merkle tree.

Concept taught: a binary tree of hashes where each internal node is the
hash of its two children. Property: changing any leaf changes the root,
and a single-leaf inclusion proof has size O(log n). That's why every
real blockchain uses one: a 1 MB block can be summarised by a 32-byte
root, and any client can verify "transaction X is in this block" with
a ~32·log2(n) byte proof rather than the whole block.

For Penumbra the leaves are encoded match-outcome transactions.

Hardening against CVE-2012-2459 (Bitcoin leaf-duplication malleability):
internal-node hashes are level-tagged, so two different leaf lists that
would once have produced the same hash at some intermediate level (e.g.
`[a, b, c]` vs `[a, b, c, c]`) now produce distinct hashes because the
duplication happens at a different level than the original pairing.
Odd-length levels are padded with a fixed zero-leaf sentinel rather than
by duplicating the last node, which would alias `[…, x]` with `[…, x, x]`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

_ZERO_LEAF: bytes = bytes(32)
_PADDING_NODE: bytes = hashlib.sha256(b"\x02penumbra-merkle-pad").digest()


def _sha256(*parts: bytes) -> bytes:
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
    return h.digest()


def hash_leaf(payload: bytes) -> bytes:
    """Domain-separated leaf hash. Prevents second-preimage between leaves and internal nodes."""
    return _sha256(b"\x00", payload)


def hash_internal(left: bytes, right: bytes, level: int = 0) -> bytes:
    """Domain-separated, level-tagged internal-node hash.

    `level` is the height of the parent node above the leaf layer (the
    first internal layer is `level=1`). Including the level prevents
    cross-level collisions that enable CVE-2012-2459-style malleability:
    a child hash from level k cannot be mistaken for a child at level
    k+1, because the parent commits to its own height.
    """
    if not 0 <= level <= 255:
        raise ValueError(f"level must fit in one byte (0..255), got {level}")
    return _sha256(b"\x01", bytes([level]), left, right)


@dataclass(frozen=True, slots=True)
class MerkleProof:
    """Inclusion proof: the sibling hashes from the leaf up to the root.

    `directions[i] is True` ↔ the sibling at level i is on the right,
    i.e. the path itself ascends on the left side.
    """

    leaf_hash: bytes
    siblings: tuple[bytes, ...]
    directions: tuple[bool, ...]


def build_root(leaves: list[bytes]) -> bytes:
    """Build a Merkle root over the byte leaves (already domain-tagged hashes)."""
    if not leaves:
        return _ZERO_LEAF
    level_nodes = [hash_leaf(leaf) for leaf in leaves]
    level = 1
    while len(level_nodes) > 1:
        if len(level_nodes) % 2 == 1:
            level_nodes.append(_PADDING_NODE)
        level_nodes = [
            hash_internal(level_nodes[i], level_nodes[i + 1], level=level)
            for i in range(0, len(level_nodes), 2)
        ]
        level += 1
    return level_nodes[0]


def build_proof(leaves: list[bytes], index: int) -> MerkleProof:
    """Build an inclusion proof for `leaves[index]`."""
    if not 0 <= index < len(leaves):
        raise IndexError(f"index {index} out of range for {len(leaves)} leaves")
    level_nodes = [hash_leaf(leaf) for leaf in leaves]
    leaf_hash = level_nodes[index]
    siblings: list[bytes] = []
    directions: list[bool] = []
    cursor = index
    level = 1
    while len(level_nodes) > 1:
        if len(level_nodes) % 2 == 1:
            level_nodes.append(_PADDING_NODE)
        sibling_idx = cursor + 1 if cursor % 2 == 0 else cursor - 1
        siblings.append(level_nodes[sibling_idx])
        directions.append(cursor % 2 == 0)  # True means our path is on the LEFT
        level_nodes = [
            hash_internal(level_nodes[i], level_nodes[i + 1], level=level)
            for i in range(0, len(level_nodes), 2)
        ]
        cursor //= 2
        level += 1
    return MerkleProof(leaf_hash=leaf_hash, siblings=tuple(siblings), directions=tuple(directions))


def verify_proof(root: bytes, proof: MerkleProof) -> bool:
    """Walk the proof from leaf to root and check we reach `root`."""
    cursor = proof.leaf_hash
    level = 1
    for sibling, on_left in zip(proof.siblings, proof.directions, strict=True):
        cursor = (
            hash_internal(cursor, sibling, level=level)
            if on_left
            else hash_internal(sibling, cursor, level=level)
        )
        level += 1
    return cursor == root
