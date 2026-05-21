"""Tests for chain disk persistence."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from penumbra_chain.block import MatchOutcome
from penumbra_chain.node import Node
from penumbra_crypto import bls


def _outcome(match_id: int) -> MatchOutcome:
    return MatchOutcome(
        match_id=match_id,
        winner_agent_id=match_id % 7,
        winning_goal=match_id % 3,
        started_tick=match_id * 50,
        end_tick=match_id * 50 + 25,
        end_reason="won",
        arena_signature=hashlib.sha256(f"a-{match_id}".encode()).digest(),
    )


def test_save_restore_roundtrip_with_blocks_and_slash() -> None:
    """Boot, produce 3 blocks, slash one validator, save, restore — everything matches."""
    node = Node.boot(n_validators=5)
    for i in range(3):
        node.submit_outcome(_outcome(i))
        node.produce_block()

    # Slash validator index 2.
    secret = node.secrets[2]
    pubkey = node.validators[2].bls_pubkey
    h_a = hashlib.sha256(b"x").digest()
    h_b = hashlib.sha256(b"y").digest()
    from penumbra_chain.consensus import canonical_block_sign_payload
    from penumbra_chain.slashing import SlashingEvidence

    evidence_height = 5
    node.slash(
        SlashingEvidence(
            offender_pubkey=pubkey,
            height=evidence_height,
            block_a_hash=h_a,
            sig_a=bls.sign(secret.bls_secret, canonical_block_sign_payload(h_a, evidence_height)),
            block_b_hash=h_b,
            sig_b=bls.sign(secret.bls_secret, canonical_block_sign_payload(h_b, evidence_height)),
        )
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        node.save_to(tmpdir)
        # Sanity: the expected files are there.
        snapshot_dir = Path(tmpdir)
        assert (snapshot_dir / "validators.json").is_file()
        assert (snapshot_dir / "secrets.json").is_file()
        assert (snapshot_dir / "state.json").is_file()
        assert (snapshot_dir / "blocks.parquet").is_file()

        restored = Node.restore_from(tmpdir)

    # Validators (pubkeys) match in order.
    assert tuple(v.bls_pubkey for v in restored.validators) == tuple(
        v.bls_pubkey for v in node.validators
    )
    # Chain length + last block hash match.
    assert restored.height == node.height
    assert restored.chain[-1].hash() == node.chain[-1].hash()
    # Slashing state preserved.
    assert restored.active_indices == node.active_indices
    assert restored.slashed_pubkeys == node.slashed_pubkeys
    # Restored node can still produce a block.
    restored.submit_outcome(_outcome(99))
    new_block = restored.produce_block()
    assert new_block is not None
    assert new_block.header.height == node.height


def test_save_with_empty_chain_and_mempool() -> None:
    node = Node.boot(n_validators=4)
    with tempfile.TemporaryDirectory() as tmpdir:
        node.save_to(tmpdir)
        restored = Node.restore_from(tmpdir)
    assert restored.height == 0
    assert len(restored.mempool) == 0
    assert restored.active_indices == {0, 1, 2, 3}


def test_save_preserves_mempool() -> None:
    node = Node.boot(n_validators=3)
    node.submit_outcome(_outcome(1))
    node.submit_outcome(_outcome(2))
    with tempfile.TemporaryDirectory() as tmpdir:
        node.save_to(tmpdir)
        restored = Node.restore_from(tmpdir)
    assert len(restored.mempool) == 2
