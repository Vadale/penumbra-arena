"""Phase 6a Tier 3 — FederatedTrainer's DP-blocked gate.

Concept taught: when the global DP mechanism's budget is exhausted,
the orchestrator flips ``FederatedTrainer.dp_blocked = True``; any
attempt to start a DP-SGD round (``dp_noise_sigma > 0``) must then
raise :class:`DPBudgetExhaustedError`. Non-DP rounds proceed as before.
"""

from __future__ import annotations

import numpy as np
import pytest
from penumbra_learning.federated import (
    DPBudgetExhaustedError,
    FederatedTrainer,
)
from penumbra_learning.mappo import MAPPO, MAPPOConfig


@pytest.fixture
def small_mappo() -> MAPPO:
    cfg = MAPPOConfig(obs_dim=18, n_actions=7, n_agents=4, hidden=16)
    return MAPPO(cfg)


def _ingest_random(trainer: FederatedTrainer, samples_per_agent: int = 32) -> None:
    rng = np.random.default_rng(7)
    obs_dim = next(iter(trainer.global_baseline.values())).shape[-1]
    n_actions = next(reversed(trainer.global_baseline.values())).shape[0]
    for agent_id in trainer.local_actors:
        for _ in range(samples_per_agent):
            obs = rng.standard_normal(size=(obs_dim,)).astype(np.float32)
            label = int(rng.integers(0, n_actions))
            trainer.ingest(agent_id, obs, label)


def test_dp_blocked_default_is_false(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    assert trainer.dp_blocked is False


def test_block_dp_then_dp_round_raises(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer.dp_noise_sigma = 1.0
    trainer.dp_l2_clip = 1.0
    trainer.local_steps = 2
    _ingest_random(trainer)
    trainer.block_dp()
    with pytest.raises(DPBudgetExhaustedError):
        trainer.step()


def test_block_dp_does_not_affect_non_dp_round(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    # dp_noise_sigma == 0 → non-DP round must succeed even when blocked.
    trainer.local_steps = 2
    _ingest_random(trainer)
    trainer.block_dp()
    record = trainer.step()
    assert record.round_id == 0


def test_unblock_dp_restores_dp_round(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer.dp_noise_sigma = 1.0
    trainer.dp_l2_clip = 1.0
    trainer.local_steps = 2
    _ingest_random(trainer)
    trainer.block_dp()
    with pytest.raises(DPBudgetExhaustedError):
        trainer.step()
    trainer.unblock_dp()
    # Now succeeds.
    record = trainer.step()
    assert record.round_id == 0


def test_block_and_unblock_are_idempotent(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer.block_dp()
    trainer.block_dp()
    assert trainer.dp_blocked is True
    trainer.unblock_dp()
    trainer.unblock_dp()
    assert trainer.dp_blocked is False
