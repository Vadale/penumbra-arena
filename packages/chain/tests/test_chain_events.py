"""Tests for Phase 6a Tier 5 — chain-as-event-source signal hook.

Concept taught: the chain ``Node`` doesn't know about the EventBus, but
it exposes an ``on_signal`` callback that the orchestrator wires into
the bus. The hook fires on (a) successful block append, with the list
of winning agent ids, and (b) successful slashing, with the offender's
validator index + the evidence height.
"""

from __future__ import annotations

import hashlib

from penumbra_chain.block import MatchOutcome
from penumbra_chain.node import Node
from penumbra_chain.slashing import SlashingEvidence
from penumbra_core.economy import Market
from penumbra_crypto import bls


def _outcome(match_id: int, winner: int | None) -> MatchOutcome:
    return MatchOutcome(
        match_id=match_id,
        winner_agent_id=winner,
        winning_goal=1,
        started_tick=match_id * 100,
        end_tick=match_id * 100 + 50,
        end_reason="won" if winner is not None else "draw",
        arena_signature=hashlib.sha256(f"a-{match_id}".encode()).digest(),
    )


def _build_evidence_for(validator_idx: int, node: Node, height: int = 42) -> SlashingEvidence:
    """Equivocation evidence for the validator at ``validator_idx``."""
    from penumbra_chain.consensus import canonical_block_sign_payload

    secret = node.secrets[validator_idx]
    block_a_hash = hashlib.sha256(b"block-a").digest()
    block_b_hash = hashlib.sha256(b"block-b").digest()
    sig_a = bls.sign(secret.bls_secret, canonical_block_sign_payload(block_a_hash, height))
    sig_b = bls.sign(secret.bls_secret, canonical_block_sign_payload(block_b_hash, height))
    return SlashingEvidence(
        offender_pubkey=node.validators[validator_idx].bls_pubkey,
        height=height,
        block_a_hash=block_a_hash,
        sig_a=sig_a,
        block_b_hash=block_b_hash,
        sig_b=sig_b,
    )


def test_produce_block_emits_chain_block_finalised() -> None:
    node = Node.boot(n_validators=4)
    signals: list[tuple[str, dict[str, object]]] = []
    node.on_signal = lambda kind, payload: signals.append((kind, payload))

    node.submit_outcome(_outcome(1, winner=7))
    block = node.produce_block()
    assert block is not None
    finalised = [s for s in signals if s[0] == "chain.block.finalised"]
    assert len(finalised) == 1
    payload = finalised[0][1]
    assert payload["height"] == 0
    assert payload["n_outcomes"] == 1
    assert payload["winners"] == [7]


def test_produce_block_winner_list_skips_none() -> None:
    """Outcomes with ``winner_agent_id is None`` (draws) are excluded."""
    node = Node.boot(n_validators=4)
    signals: list[tuple[str, dict[str, object]]] = []
    node.on_signal = lambda kind, payload: signals.append((kind, payload))

    node.submit_outcome(_outcome(1, winner=3))
    node.submit_outcome(_outcome(2, winner=None))
    node.submit_outcome(_outcome(3, winner=5))
    block = node.produce_block()
    assert block is not None
    finalised = [s for s in signals if s[0] == "chain.block.finalised"]
    assert len(finalised) == 1
    assert finalised[0][1]["winners"] == [3, 5]
    assert finalised[0][1]["n_outcomes"] == 3


def test_slash_emits_chain_validator_slashed() -> None:
    node = Node.boot(n_validators=4)
    signals: list[tuple[str, dict[str, object]]] = []
    node.on_signal = lambda kind, payload: signals.append((kind, payload))

    ev = _build_evidence_for(2, node, height=42)
    node.slash(ev)
    slashed = [s for s in signals if s[0] == "chain.validator.slashed"]
    assert len(slashed) == 1
    payload = slashed[0][1]
    assert payload["validator_id"] == 2
    assert payload["evidence_height"] == 42


def test_node_without_on_signal_does_not_raise() -> None:
    """The hook is optional — None must be the default + safe."""
    node = Node.boot(n_validators=4)
    assert node.on_signal is None
    node.submit_outcome(_outcome(1, winner=0))
    block = node.produce_block()
    assert block is not None


def test_market_credit_block_winners_adds_reward_to_each() -> None:
    market = Market.build(nodes=[0, 1, 2], n_agents=4, seed=42)
    before_1 = market.wallets[1].coins
    before_2 = market.wallets[2].coins
    market.credit_block_winners([1, 2])
    assert market.wallets[1].coins == before_1 + market.block_reward_coins
    assert market.wallets[2].coins == before_2 + market.block_reward_coins


def test_market_credit_block_winners_skips_unknown_ids() -> None:
    market = Market.build(nodes=[0], n_agents=2, seed=1)
    before_0 = market.wallets[0].coins
    market.credit_block_winners([0, 999])  # 999 doesn't exist
    assert market.wallets[0].coins == before_0 + market.block_reward_coins


def test_market_credit_block_winners_duplicates_credit_twice() -> None:
    """Mirrors the chain's view: a winner appearing twice gets paid twice."""
    market = Market.build(nodes=[0], n_agents=2, seed=1)
    before_1 = market.wallets[1].coins
    market.credit_block_winners([1, 1])
    assert market.wallets[1].coins == before_1 + 2 * market.block_reward_coins
