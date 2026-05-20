"""SHA-256 Merkle tree.

Concept taught: a binary tree of hashes where each internal node is the
hash of its two children. Property: changing any leaf changes the root,
and a single-leaf inclusion proof has size O(log n). That's why every
real blockchain uses one: a 1 MB block can be summarised by a 32-byte
root, and any client can verify "transaction X is in this block" with
a ~32·log2(n) byte proof rather than the whole block.

For Penumbra the leaves are encoded match-outcome transactions.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

_ZERO_LEAF: bytes = bytes(32)


def _sha256(*parts: bytes) -> bytes:
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
    return h.digest()


def hash_leaf(payload: bytes) -> bytes:
    """Domain-separated leaf hash. Prevents second-preimage between leaves and internal nodes."""
    return _sha256(b"\x00", payload)


def hash_internal(left: bytes, right: bytes) -> bytes:
    """Domain-separated internal-node hash."""
    return _sha256(b"\x01", left, right)


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
    level = [hash_leaf(leaf) for leaf in leaves]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])  # duplicate the last node (Bitcoin-style)
        level = [hash_internal(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def build_proof(leaves: list[bytes], index: int) -> MerkleProof:
    """Build an inclusion proof for `leaves[index]`."""
    if not 0 <= index < len(leaves):
        raise IndexError(f"index {index} out of range for {len(leaves)} leaves")
    level = [hash_leaf(leaf) for leaf in leaves]
    leaf_hash = level[index]
    siblings: list[bytes] = []
    directions: list[bool] = []
    cursor = index
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        sibling_idx = cursor + 1 if cursor % 2 == 0 else cursor - 1
        siblings.append(level[sibling_idx])
        directions.append(cursor % 2 == 0)  # True means our path is on the LEFT
        level = [hash_internal(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        cursor //= 2
    return MerkleProof(leaf_hash=leaf_hash, siblings=tuple(siblings), directions=tuple(directions))


def verify_proof(root: bytes, proof: MerkleProof) -> bool:
    """Walk the proof from leaf to root and check we reach `root`."""
    cursor = proof.leaf_hash
    for sibling, on_left in zip(proof.siblings, proof.directions, strict=True):
        cursor = hash_internal(cursor, sibling) if on_left else hash_internal(sibling, cursor)
    return cursor == root
