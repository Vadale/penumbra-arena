"""Tests for the slashing pathway."""

from __future__ import annotations

import hashlib

import pytest
from penumbra_chain.block import MatchOutcome
from penumbra_chain.node import Node, QuorumFailedError
from penumbra_chain.slashing import (
    SlashingError,
    SlashingEvidence,
    is_valid_evidence,
    verify_evidence,
)
from penumbra_crypto import bls


def _outcome(match_id: int) -> MatchOutcome:
    return MatchOutcome(
        match_id=match_id,
        winner_agent_id=0,
        winning_goal=1,
        started_tick=match_id * 100,
        end_tick=match_id * 100 + 50,
        end_reason="won",
        arena_signature=hashlib.sha256(f"a-{match_id}".encode()).digest(),
    )


def _build_evidence_for(validator_idx: int, node: Node) -> SlashingEvidence:
    """Equivocation evidence: same validator signs two distinct block hashes."""
    secret = node.secrets[validator_idx]
    block_a_hash = hashlib.sha256(b"block-a").digest()
    block_b_hash = hashlib.sha256(b"block-b").digest()
    sig_a = bls.sign(secret.bls_secret, block_a_hash)
    sig_b = bls.sign(secret.bls_secret, block_b_hash)
    return SlashingEvidence(
        offender_pubkey=node.validators[validator_idx].bls_pubkey,
        block_a_hash=block_a_hash,
        sig_a=sig_a,
        block_b_hash=block_b_hash,
        sig_b=sig_b,
    )


def test_is_valid_evidence_rejects_same_hashes() -> None:
    h = hashlib.sha256(b"x").digest()
    ev = SlashingEvidence(
        offender_pubkey=b"\x00" * bls.PUBLIC_KEY_BYTES,
        block_a_hash=h,
        sig_a=b"\x00" * bls.SIGNATURE_BYTES,
        block_b_hash=h,
        sig_b=b"\x00" * bls.SIGNATURE_BYTES,
    )
    assert not is_valid_evidence(ev)


def test_verify_evidence_accepts_real_sigs() -> None:
    node = Node.boot(n_validators=4)
    ev = _build_evidence_for(0, node)
    assert verify_evidence(ev)


def test_verify_evidence_rejects_tampered_sig() -> None:
    node = Node.boot(n_validators=4)
    ev = _build_evidence_for(0, node)
    bad_sig_a = bytearray(ev.sig_a)
    bad_sig_a[0] ^= 0xFF
    tampered = SlashingEvidence(
        offender_pubkey=ev.offender_pubkey,
        block_a_hash=ev.block_a_hash,
        sig_a=bytes(bad_sig_a),
        block_b_hash=ev.block_b_hash,
        sig_b=ev.sig_b,
    )
    assert not verify_evidence(tampered)


def test_slash_removes_validator_from_active_set() -> None:
    node = Node.boot(n_validators=6)
    assert len(node.active_indices) == 6
    ev = _build_evidence_for(2, node)
    tx = node.slash(ev)
    assert 2 not in node.active_indices
    assert len(node.active_indices) == 5
    assert ev.offender_pubkey in node.slashed_pubkeys
    assert tx in node.pending_slashings


def test_slash_rejects_already_slashed() -> None:
    """Per crypto-audit A2/A3: re-submitting evidence must raise, not no-op.

    The previous behaviour fabricated a fresh SlashingTx from caller-
    supplied data and returned it — which the HTTP layer treated as
    canonical. That made the API a small forgery vector. Now we refuse.
    """
    node = Node.boot(n_validators=4)
    ev = _build_evidence_for(1, node)
    node.slash(ev)
    with pytest.raises(SlashingError, match="already slashed"):
        node.slash(ev)
    # And the active set still shows the validator slashed once.
    assert len(node.active_indices) == 3


def test_slash_rejects_unknown_offender() -> None:
    node = Node.boot(n_validators=4)
    other = Node.boot(n_validators=1)
    ev = _build_evidence_for(0, other)
    with pytest.raises(SlashingError, match="not in our validator set"):
        node.slash(ev)


def test_slash_rejects_bad_evidence() -> None:
    node = Node.boot(n_validators=4)
    h = hashlib.sha256(b"x").digest()
    bad_ev = SlashingEvidence(
        offender_pubkey=node.validators[0].bls_pubkey,
        block_a_hash=h,
        sig_a=b"\x00" * bls.SIGNATURE_BYTES,
        block_b_hash=hashlib.sha256(b"y").digest(),
        sig_b=b"\x00" * bls.SIGNATURE_BYTES,
    )
    with pytest.raises(SlashingError, match="cryptographic verification"):
        node.slash(bad_ev)


def test_block_production_after_slash_uses_active_quorum() -> None:
    """After slashing 2 of 6 validators, blocks still finalise with the
    remaining 4 (whose 2/3-of-4 = 3 threshold is met)."""
    node = Node.boot(n_validators=6)
    node.slash(_build_evidence_for(0, node))
    node.slash(_build_evidence_for(1, node))
    assert len(node.active_indices) == 4
    node.submit_outcome(_outcome(1))
    block = node.produce_block()
    assert block is not None
    assert block.validator_pubkeys  # finality bundle exists


def test_slashing_below_quorum_raises_on_next_block() -> None:
    """If we slash too many validators we cannot finalise anything."""
    node = Node.boot(n_validators=3)
    node.slash(_build_evidence_for(0, node))
    node.slash(_build_evidence_for(1, node))
    # Only 1 active validator; ceil(2*1/3) = 1, so threshold can still pass.
    # Add a third slash to drop us below quorum entirely.
    node.slash(_build_evidence_for(2, node))
    node.submit_outcome(_outcome(1))
    with pytest.raises(QuorumFailedError):
        node.produce_block()


def test_slashing_lands_in_next_block_payload() -> None:
    """A submitted slashing must appear in `block.slashings` after produce_block."""
    node = Node.boot(n_validators=5)
    ev = _build_evidence_for(3, node)
    node.slash(ev)
    block = node.produce_block()
    assert block is not None
    assert len(block.slashings) == 1
    assert block.slashings[0].evidence.offender_pubkey == ev.offender_pubkey
    assert node.pending_slashings == []


def test_merkle_root_changes_when_slashing_added() -> None:
    """Two otherwise-identical blocks differ in merkle root if one has a slashing."""
    from penumbra_chain.block import Block
    from penumbra_chain.slashing import SlashingTx

    h = bytes(32)
    proposer = bytes(48)
    vrf_beta = bytes(32)
    timestamp = 12345
    block_no_slash = Block.assemble(
        height=0,
        prev_hash=h,
        proposer_pubkey=proposer,
        vrf_beta=vrf_beta,
        timestamp_ns=timestamp,
        payload=(),
    )
    node = Node.boot(n_validators=2)
    ev = _build_evidence_for(0, node)
    slashing = SlashingTx(evidence=ev, height_observed=0)
    block_with_slash = Block.assemble(
        height=0,
        prev_hash=h,
        proposer_pubkey=proposer,
        vrf_beta=vrf_beta,
        timestamp_ns=timestamp,
        payload=(),
        slashings=(slashing,),
    )
    assert block_no_slash.header.merkle_root != block_with_slash.header.merkle_root
