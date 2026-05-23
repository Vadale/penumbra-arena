"""End-to-end smoke test for Phase 6a Tier 5.

Concept taught: an outcome submitted to the chain mempool → on
``produce_block``, the node fires ``on_signal`` → the orchestrator
forwards onto the EventBus → the registered handler credits the
winner's wallet. Three pillars (chain, transport, core economy) close
the loop in one tick.
"""

from __future__ import annotations

import hashlib

from penumbra_chain.block import MatchOutcome
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_transport.orchestrator import Orchestrator


def _outcome(match_id: int, winner: int) -> MatchOutcome:
    return MatchOutcome(
        match_id=match_id,
        winner_agent_id=winner,
        winning_goal=1,
        started_tick=match_id * 100,
        end_tick=match_id * 100 + 50,
        end_reason="won",
        arena_signature=hashlib.sha256(f"a-{match_id}".encode()).digest(),
    )


def test_chain_block_finalised_credits_winner_wallet_end_to_end() -> None:
    sim = Simulation.build(SimulationConfig(n_agents=4, match_max_ticks=50), bootstrap(seed=11))
    orch = Orchestrator.build(sim, n_validators=4)
    assert orch.market is not None
    winner_id = 2
    before = orch.market.wallets[winner_id].coins  # type: ignore[attr-defined]
    reward = orch.market.block_reward_coins  # type: ignore[attr-defined]

    orch.node.submit_outcome(_outcome(1, winner=winner_id))
    block = orch.node.produce_block()
    assert block is not None

    kinds = [e.kind for e in orch.event_bus.recent(limit=50)]
    assert "chain.block.finalised" in kinds

    after = orch.market.wallets[winner_id].coins  # type: ignore[attr-defined]
    assert after == before + reward
