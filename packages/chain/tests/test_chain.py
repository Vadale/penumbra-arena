"""End-to-end tests for the Penumbra chain stack."""

from __future__ import annotations

import hashlib

from penumbra_chain import merkle
from penumbra_chain.block import GENESIS_PREV_HASH, Block, MatchOutcome
from penumbra_chain.consensus import (
    elect_leader,
    finalise,
    keygen,
    sign_block_hash,
    verify_leader,
)
from penumbra_chain.mempool import Mempool
from penumbra_chain.node import Node

# ── Merkle ────────────────────────────────────────────────────────


def test_merkle_empty_root_is_deterministic() -> None:
    assert merkle.build_root([]) == bytes(32)


def test_merkle_single_leaf_round_trips() -> None:
    leaves = [b"alpha"]
    root = merkle.build_root(leaves)
    proof = merkle.build_proof(leaves, 0)
    assert merkle.verify_proof(root, proof)


def test_merkle_multi_leaf_round_trips() -> None:
    leaves = [f"leaf-{i}".encode() for i in range(13)]
    root = merkle.build_root(leaves)
    for i in range(len(leaves)):
        proof = merkle.build_proof(leaves, i)
        assert merkle.verify_proof(root, proof), f"index {i} should verify"


def test_merkle_proof_rejects_after_tamper() -> None:
    leaves = [b"a", b"b", b"c", b"d"]
    root = merkle.build_root(leaves)
    proof = merkle.build_proof(leaves, 1)
    tampered = merkle.MerkleProof(
        leaf_hash=hashlib.sha256(b"\x00z").digest(),
        siblings=proof.siblings,
        directions=proof.directions,
    )
    assert not merkle.verify_proof(root, tampered)


def test_merkle_changing_any_leaf_changes_root() -> None:
    a = merkle.build_root([b"x", b"y", b"z"])
    b = merkle.build_root([b"x", b"y", b"Z"])
    assert a != b


# ── Block ─────────────────────────────────────────────────────────


def _outcome(match_id: int) -> MatchOutcome:
    return MatchOutcome(
        match_id=match_id,
        winner_agent_id=match_id % 10,
        winning_goal=match_id % 5,
        started_tick=match_id * 100,
        end_tick=match_id * 100 + 50,
        end_reason="won",
        arena_signature=hashlib.sha256(f"arena-{match_id}".encode()).digest(),
    )


def test_block_hash_is_stable() -> None:
    blk = Block.assemble(
        height=0,
        prev_hash=GENESIS_PREV_HASH,
        proposer_pubkey=b"\x01" * 48,
        vrf_beta=b"\x02" * 32,
        timestamp_ns=1_700_000_000_000_000_000,
        payload=(_outcome(1), _outcome(2)),
    )
    assert blk.hash() == blk.hash()  # determinism


def test_block_hash_changes_with_payload() -> None:
    a = Block.assemble(
        height=0,
        prev_hash=GENESIS_PREV_HASH,
        proposer_pubkey=b"\x01" * 48,
        vrf_beta=b"\x02" * 32,
        timestamp_ns=0,
        payload=(_outcome(1),),
    )
    b = Block.assemble(
        height=0,
        prev_hash=GENESIS_PREV_HASH,
        proposer_pubkey=b"\x01" * 48,
        vrf_beta=b"\x02" * 32,
        timestamp_ns=0,
        payload=(_outcome(2),),
    )
    assert a.hash() != b.hash()


# ── Consensus ─────────────────────────────────────────────────────


def test_validator_keygen_self_consistent() -> None:
    ident, _ = keygen()
    assert ident.is_self_consistent()


def test_leader_election_and_verification() -> None:
    validators = []
    secrets = []
    for _ in range(5):
        ident, secret = keygen()
        validators.append(ident)
        secrets.append(secret)
    seed = b"penumbra-block-1"
    leader_idx, output = elect_leader(validators, secrets, seed)
    assert 0 <= leader_idx < 5
    assert verify_leader(validators, seed, leader_idx, output)


def test_finality_requires_two_thirds() -> None:
    validators = []
    secrets = []
    for _ in range(6):  # threshold = ceil(2*6/3) = 4
        ident, secret = keygen()
        validators.append(ident)
        secrets.append(secret)
    block_hash = hashlib.sha256(b"block").digest()
    height = 7
    # Only 3 validators sign — below threshold.
    sigs_short = [
        (v.bls_pubkey, sign_block_hash(s, block_hash, height))
        for v, s in list(zip(validators, secrets, strict=True))[:3]
    ]
    assert finalise(block_hash, height, sigs_short, total_validators=6) is None

    # 4 sign — meets the ceiling.
    sigs_ok = [
        (v.bls_pubkey, sign_block_hash(s, block_hash, height))
        for v, s in list(zip(validators, secrets, strict=True))[:4]
    ]
    result = finalise(block_hash, height, sigs_ok, total_validators=6)
    assert result is not None


def test_finality_rejects_invalid_signature() -> None:
    validators = []
    secrets = []
    for _ in range(4):
        ident, secret = keygen()
        validators.append(ident)
        secrets.append(secret)
    block_hash = hashlib.sha256(b"x").digest()
    height = 11
    sigs = [
        (v.bls_pubkey, sign_block_hash(s, block_hash, height))
        for v, s in zip(validators, secrets, strict=True)
    ]
    # Replace one signature with garbage — only 3 valid sigs remain
    # which is below ceil(2*4/3) = 3 — wait, that's *exactly* 3.
    sigs[-1] = (sigs[-1][0], b"\x00" * 96)
    result = finalise(block_hash, height, sigs, total_validators=4)
    assert result is not None  # 3 valid = threshold


# ── Mempool ───────────────────────────────────────────────────────


def test_mempool_drain_is_fifo() -> None:
    m = Mempool(capacity=8)
    m.submit(_outcome(1))
    m.submit(_outcome(2))
    m.submit(_outcome(3))
    drained = m.drain(2)
    assert [d.match_id for d in drained] == [1, 2]
    assert len(m) == 1


def test_mempool_capacity_drops_oldest() -> None:
    m = Mempool(capacity=2)
    m.submit(_outcome(1))
    m.submit(_outcome(2))
    m.submit(_outcome(3))
    drained = m.drain(2)
    assert [d.match_id for d in drained] == [2, 3]


# ── Node ──────────────────────────────────────────────────────────


def test_node_boot_and_produce_block() -> None:
    node = Node.boot(n_validators=4)
    assert node.height == 0
    node.submit_outcome(_outcome(1))
    node.submit_outcome(_outcome(2))
    block = node.produce_block()
    assert block is not None
    assert node.height == 1
    assert block.header.height == 0
    assert block.header.prev_hash == bytes(32)
    assert len(block.payload) == 2


def test_node_chain_links_prev_hash() -> None:
    node = Node.boot(n_validators=4)
    node.submit_outcome(_outcome(1))
    b0 = node.produce_block()
    node.submit_outcome(_outcome(2))
    b1 = node.produce_block()
    assert b0 is not None
    assert b1 is not None
    assert b1.header.prev_hash == b0.hash()
    assert b1.header.height == 1


def test_node_empty_mempool_no_block() -> None:
    node = Node.boot(n_validators=3)
    assert node.produce_block() is None


def test_node_finalised_block_has_pubkeys_and_aggregate() -> None:
    node = Node.boot(n_validators=4)
    node.submit_outcome(_outcome(1))
    block = node.produce_block()
    assert block is not None
    assert len(block.validator_pubkeys) >= 3  # ceil(2*4/3) = 3
    assert len(block.aggregate_signature) == 96
