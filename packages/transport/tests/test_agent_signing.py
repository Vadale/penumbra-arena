"""Tests for the per-agent Dilithium keystore + canonical message bytes."""

from __future__ import annotations

from penumbra_transport.agent_signing import (
    AgentKeystore,
    canonical_move_bytes,
)


def test_canonical_message_is_stable() -> None:
    a = canonical_move_bytes(tick=42, agent_id=7, target_node=3)
    b = canonical_move_bytes(tick=42, agent_id=7, target_node=3)
    assert a == b


def test_canonical_message_changes_with_tick() -> None:
    a = canonical_move_bytes(tick=42, agent_id=7, target_node=3)
    b = canonical_move_bytes(tick=43, agent_id=7, target_node=3)
    assert a != b


def test_canonical_message_changes_with_agent() -> None:
    a = canonical_move_bytes(tick=42, agent_id=7, target_node=3)
    b = canonical_move_bytes(tick=42, agent_id=8, target_node=3)
    assert a != b


def test_keystore_sign_verify_roundtrip() -> None:
    keystore = AgentKeystore.for_n_agents(3)
    sig = keystore.sign_move(agent_id=1, tick=10, target_node=5)
    assert keystore.verify_move(agent_id=1, tick=10, target_node=5, signature=sig)
    assert keystore.stats.verified == 1
    assert keystore.stats.rejected == 0


def test_keystore_rejects_replayed_signature_at_other_tick() -> None:
    """The signature is over the tick; replaying it later must fail."""
    keystore = AgentKeystore.for_n_agents(3)
    sig = keystore.sign_move(agent_id=2, tick=100, target_node=7)
    # Replay at a later tick — must reject.
    assert not keystore.verify_move(agent_id=2, tick=101, target_node=7, signature=sig)
    assert keystore.stats.rejected == 1


def test_keystore_rejects_cross_agent_signature() -> None:
    """A sig from agent 0 must not verify under agent 1's key."""
    keystore = AgentKeystore.for_n_agents(3)
    sig = keystore.sign_move(agent_id=0, tick=10, target_node=4)
    assert not keystore.verify_move(agent_id=1, tick=10, target_node=4, signature=sig)


def test_keystore_rejects_unknown_agent_id() -> None:
    keystore = AgentKeystore.for_n_agents(2)
    assert not keystore.verify_move(
        agent_id=99,
        tick=10,
        target_node=4,
        signature=b"\x00" * 3309,
    )
