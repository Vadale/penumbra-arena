"""Federated learning Tier 1+2+3+4 tests (real local SGD)."""

from __future__ import annotations

import numpy as np
import pytest
import torch
from penumbra_learning.federated import (
    FederatedTrainer,
    LocalActor,
    fedavg,
    krum,
    trimmed_mean,
)
from penumbra_learning.mappo import MAPPO, MAPPOConfig


@pytest.fixture
def small_mappo() -> MAPPO:
    cfg = MAPPOConfig(obs_dim=18, n_actions=7, n_agents=5, hidden=16)
    return MAPPO(cfg)


def _ingest_random(trainer: FederatedTrainer, samples_per_agent: int = 32) -> None:
    """Fill each LocalActor's buffer with random (obs, label) so SGD has data."""
    rng = np.random.default_rng(42)
    obs_dim = next(iter(trainer.global_baseline.values())).shape[-1]
    n_actions = next(reversed(trainer.global_baseline.values())).shape[0]
    for agent_id in trainer.local_actors:
        for _ in range(samples_per_agent):
            obs = rng.standard_normal(size=(obs_dim,)).astype(np.float32)
            label = int(rng.integers(0, n_actions))
            trainer.ingest(agent_id, obs, label)


# ── functional aggregators (no trainer) ─────────────────────────────


def test_fedavg_returns_elementwise_mean() -> None:
    u1 = {"w": torch.tensor([1.0, 2.0])}
    u2 = {"w": torch.tensor([3.0, 4.0])}
    out = fedavg([u1, u2])
    assert torch.allclose(out["w"], torch.tensor([2.0, 3.0]))


def test_fedavg_empty_input_returns_empty() -> None:
    assert fedavg([]) == {}


def test_krum_picks_central_update_when_n_sufficient() -> None:
    honest = [{"w": torch.tensor([0.01, 0.02])} for _ in range(5)]
    outlier = {"w": torch.tensor([100.0, 100.0])}
    winner = krum([*honest, outlier], f=1)
    assert not torch.allclose(winner["w"], outlier["w"])


def test_krum_fallback_to_fedavg_when_n_too_small() -> None:
    updates = [
        {"w": torch.tensor([0.0])},
        {"w": torch.tensor([2.0])},
    ]
    out = krum(updates, f=1)
    assert torch.allclose(out["w"], torch.tensor([1.0]))


def test_trimmed_mean_drops_outliers() -> None:
    updates = [
        {"w": torch.tensor([1.0])},
        {"w": torch.tensor([2.0])},
        {"w": torch.tensor([3.0])},
        {"w": torch.tensor([100.0])},
        {"w": torch.tensor([4.0])},
    ]
    out = trimmed_mean(updates, trim_fraction=0.2)
    assert torch.allclose(out["w"], torch.tensor([3.0]))


# ── LocalActor ───────────────────────────────────────────────────────


def test_local_actor_fresh_clones_template(small_mappo: MAPPO) -> None:
    template = small_mappo.actor
    actor = LocalActor.fresh(agent_id=0, template=template)
    assert actor.agent_id == 0
    assert actor.buffer_size == 0
    # Clone weights match template exactly.
    template_params = dict(template.named_parameters())
    for name, p in actor.actor.named_parameters():
        assert torch.allclose(p.detach().cpu(), template_params[name].detach().cpu())


def test_local_actor_ingest_grows_buffer(small_mappo: MAPPO) -> None:
    actor = LocalActor.fresh(agent_id=0, template=small_mappo.actor)
    actor.ingest(np.zeros(18, dtype=np.float32), label=3)
    actor.ingest(np.ones(18, dtype=np.float32), label=5)
    assert actor.buffer_size == 2
    assert list(actor.labels) == [3, 5]


def test_local_actor_load_weights_overrides(small_mappo: MAPPO) -> None:
    actor = LocalActor.fresh(agent_id=0, template=small_mappo.actor)
    zero_weights = {name: torch.zeros_like(p) for name, p in actor.actor.named_parameters()}
    actor.load_weights(zero_weights)
    for _, p in actor.actor.named_parameters():
        assert torch.all(p == 0)


# ── FederatedTrainer ─────────────────────────────────────────────────


def test_federated_trainer_initialises_from_mappo(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    assert len(trainer.local_actors) == 3
    assert set(trainer.global_baseline.keys()) == {
        name for name, _ in small_mappo.actor.named_parameters()
    }


def test_federated_trainer_rejects_bad_method(small_mappo: MAPPO) -> None:
    with pytest.raises(ValueError, match="unknown method"):
        FederatedTrainer.from_mappo(small_mappo, n_agents=3, method="lolwhat")


def test_set_method_rejects_unknown(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    with pytest.raises(ValueError, match="unknown method"):
        trainer.set_method("lolwhat")


def test_set_method_accepts_each_supported(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    for method in ("fedavg", "ckks_sum", "krum", "trimmed_mean"):
        trainer.set_method(method)
        assert trainer.aggregation_method == method


def test_federated_step_records_round(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer.local_steps = 2
    _ingest_random(trainer)
    record = trainer.step()
    assert record.round_id == 0
    assert record.n_participants == 3
    assert record.aggregation_method == "fedavg"
    assert not record.encrypted
    assert record.bandwidth_bytes > 0


def test_federated_real_sgd_moves_loss_down(small_mappo: MAPPO) -> None:
    """With real SGD on a fixed (obs, label) buffer, mean loss must drop."""
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer.local_steps = 50
    trainer.local_lr = 0.05
    _ingest_random(trainer, samples_per_agent=64)
    r0 = trainer.step()
    trainer.step()
    r2 = trainer.step()
    # Loss should be measurable and trending down across rounds.
    assert r0.mean_local_loss > 0.0
    # Last round's loss should be lower than the first by a clear margin.
    assert r2.mean_local_loss < r0.mean_local_loss


def test_federated_step_advances_baseline(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer.local_steps = 4
    _ingest_random(trainer)
    before = {k: v.clone() for k, v in trainer.global_baseline.items()}
    trainer.step()
    moved = any(
        not torch.allclose(before[k], trainer.global_baseline[k], atol=1e-7) for k in before
    )
    assert moved


def test_federated_step_broadcasts_new_baseline(small_mappo: MAPPO) -> None:
    """After step(), every LocalActor's weights == global_baseline."""
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    _ingest_random(trainer)
    trainer.step()
    for state in trainer.local_actors.values():
        local = state.weights()
        for name in trainer.global_baseline:
            assert torch.allclose(local[name], trainer.global_baseline[name], atol=1e-6)


# ── Aggregation method routing ──────────────────────────────────────


def test_ckks_sum_aggregation_runs(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3, method="ckks_sum")
    trainer.local_steps = 2
    _ingest_random(trainer)
    record = trainer.step()
    assert record.encrypted
    assert record.aggregation_method == "ckks_sum"


def test_ckks_sum_reports_encrypted_true(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3, method="ckks_sum")
    trainer.local_steps = 1
    _ingest_random(trainer)
    record = trainer.step()
    assert record.encrypted is True


def test_ckks_sum_produces_close_to_fedavg(small_mappo: MAPPO) -> None:
    """CKKS-encrypted sum/N must approximate FedAvg up to CKKS noise."""
    n_agents = 3
    local_steps = 2

    fedavg_trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=n_agents, method="fedavg")
    fedavg_trainer.local_steps = local_steps
    _ingest_random(fedavg_trainer)
    ckks_trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=n_agents, method="ckks_sum")
    ckks_trainer.local_steps = local_steps
    _ingest_random(ckks_trainer)

    fedavg_trainer.step()
    ckks_trainer.step()

    max_abs_diff = 0.0
    for name in fedavg_trainer.global_baseline:
        diff = (
            (fedavg_trainer.global_baseline[name] - ckks_trainer.global_baseline[name])
            .abs()
            .max()
            .item()
        )
        max_abs_diff = max(max_abs_diff, float(diff))
    assert max_abs_diff < 0.1, f"CKKS aggregation drifted too far from FedAvg: {max_abs_diff}"


def test_ckks_sum_bandwidth_is_realistic(small_mappo: MAPPO) -> None:
    """Real CKKS ciphertexts are large; plain-float FedAvg is small."""
    fedavg_trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3, method="fedavg")
    fedavg_trainer.local_steps = 1
    _ingest_random(fedavg_trainer)
    fedavg_record = fedavg_trainer.step()

    ckks_trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3, method="ckks_sum")
    ckks_trainer.local_steps = 1
    _ingest_random(ckks_trainer)
    ckks_record = ckks_trainer.step()

    assert ckks_record.bandwidth_bytes > 1024
    assert ckks_record.bandwidth_bytes > fedavg_record.bandwidth_bytes


def test_krum_aggregation_runs_when_n_sufficient(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=5, method="krum")
    trainer.local_steps = 2
    _ingest_random(trainer)
    record = trainer.step()
    assert record.aggregation_method == "krum"
    assert not record.encrypted


def test_trimmed_mean_aggregation_runs(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=5, method="trimmed_mean")
    trainer.local_steps = 2
    _ingest_random(trainer)
    record = trainer.step()
    assert record.aggregation_method == "trimmed_mean"


# ── DP-SGD knobs (Tier 3) ───────────────────────────────────────────


def test_dp_sgd_clipping_records_privacy_spend(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=2)
    trainer.dp_l2_clip = 0.1
    trainer.dp_noise_sigma = 0.01
    trainer.local_steps = 4
    _ingest_random(trainer)
    record = trainer.step()
    for state in trainer.local_actors.values():
        assert state.privacy_spent > 0
    assert record.round_id == 0


# ── ingest path ─────────────────────────────────────────────────────


def test_trainer_ingest_routes_to_correct_actor(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer.ingest(agent_id=1, obs=np.zeros(18, dtype=np.float32), label=4)
    assert trainer.local_actors[1].buffer_size == 1
    assert trainer.local_actors[0].buffer_size == 0
    assert trainer.local_actors[2].buffer_size == 0


def test_trainer_ingest_unknown_agent_is_noop(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer.ingest(agent_id=99, obs=np.zeros(18, dtype=np.float32), label=0)
    for s in trainer.local_actors.values():
        assert s.buffer_size == 0
