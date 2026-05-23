"""Unit tests for the Rényi DP accountant (Tier 3)."""

from __future__ import annotations

import math

import numpy as np
import pytest
import torch
from penumbra_learning.federated import FederatedTrainer
from penumbra_learning.federated_dp import (
    EpsilonDeltaReport,
    RDPAccountant,
    RDPAccountantError,
)
from penumbra_learning.mappo import MAPPO, MAPPOConfig

# ── accountant primitives ────────────────────────────────────────────


def test_accountant_zero_epsilon_at_start() -> None:
    acc = RDPAccountant()
    assert acc.epsilon(target_delta=1e-5) == 0.0
    assert acc.n_steps == 0
    assert all(r == 0.0 for r in acc.rdp_values)


def test_accountant_epsilon_grows_with_more_steps() -> None:
    sigma = 1.0
    q = 0.01
    acc = RDPAccountant()
    epsilons: list[float] = []
    for _ in range(20):
        acc.step(noise_multiplier=sigma, sample_rate=q)
        epsilons.append(acc.epsilon(target_delta=1e-5))
    # Strictly increasing — every SGM step costs privacy.
    diffs = np.diff(epsilons)
    assert (diffs > 0).all(), f"epsilon must grow monotonically: {epsilons}"


def test_accountant_higher_sigma_means_smaller_epsilon() -> None:
    q = 0.01
    n_steps = 50
    acc_low = RDPAccountant()
    acc_high = RDPAccountant()
    for _ in range(n_steps):
        acc_low.step(noise_multiplier=0.5, sample_rate=q)
        acc_high.step(noise_multiplier=4.0, sample_rate=q)
    eps_low = acc_low.epsilon(target_delta=1e-5)
    eps_high = acc_high.epsilon(target_delta=1e-5)
    assert eps_high < eps_low, f"sigma↑ should shrink ε; got low={eps_low} high={eps_high}"


def test_accountant_full_batch_matches_gaussian_mechanism() -> None:
    """When q=1 the SGM degenerates to plain Gaussian: RDP = α / (2σ²)."""
    sigma = 2.0
    acc = RDPAccountant(orders=[2.0, 4.0, 8.0])
    acc.step(noise_multiplier=sigma, sample_rate=1.0)
    expected = [alpha / (2.0 * sigma**2) for alpha in acc.orders]
    for got, exp in zip(acc.rdp_values, expected, strict=True):
        assert math.isclose(got, exp, rel_tol=1e-9, abs_tol=1e-12)


def test_accountant_rejects_bad_sigma() -> None:
    acc = RDPAccountant()
    with pytest.raises(RDPAccountantError):
        acc.step(noise_multiplier=0.0, sample_rate=0.01)
    with pytest.raises(RDPAccountantError):
        acc.step(noise_multiplier=-1.0, sample_rate=0.01)


def test_accountant_rejects_bad_sample_rate() -> None:
    acc = RDPAccountant()
    with pytest.raises(RDPAccountantError):
        acc.step(noise_multiplier=1.0, sample_rate=0.0)
    with pytest.raises(RDPAccountantError):
        acc.step(noise_multiplier=1.0, sample_rate=1.5)


def test_accountant_rejects_empty_orders() -> None:
    with pytest.raises(RDPAccountantError):
        RDPAccountant(orders=[])


def test_accountant_rejects_order_le_one() -> None:
    with pytest.raises(RDPAccountantError):
        RDPAccountant(orders=[0.5, 2.0])
    with pytest.raises(RDPAccountantError):
        RDPAccountant(orders=[1.0, 2.0])


def test_accountant_rejects_bad_delta() -> None:
    acc = RDPAccountant()
    acc.step(noise_multiplier=1.0, sample_rate=0.01)
    with pytest.raises(RDPAccountantError):
        acc.epsilon(target_delta=0.0)
    with pytest.raises(RDPAccountantError):
        acc.epsilon(target_delta=1.0)


def test_accountant_report_returns_curve() -> None:
    acc = RDPAccountant()
    for _ in range(5):
        acc.step(noise_multiplier=1.0, sample_rate=0.05)
    report = acc.report(target_delta=1e-5)
    assert isinstance(report, EpsilonDeltaReport)
    assert report.n_steps == 5
    assert report.delta == 1e-5
    assert len(report.orders) == len(report.rdp_values)
    assert report.epsilon > 0.0
    # All RDP values should be > 0 after composition under non-trivial sigma.
    assert all(r > 0.0 for r in report.rdp_values)


# ── trainer integration ────────────────────────────────────────────


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


def test_trainer_lazily_instantiates_accountant_on_dp_step(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    assert trainer.rdp_accountant is None
    # No DP — accountant stays None.
    _ingest_random(trainer)
    trainer.local_steps = 2
    trainer.step()
    assert trainer.rdp_accountant is None
    # Enable DP — accountant should appear after one round.
    trainer.dp_noise_sigma = 1.0
    trainer.dp_l2_clip = 1.0
    trainer.step()
    assert trainer.rdp_accountant is not None
    assert trainer.rdp_accountant.n_steps > 0


def test_trainer_epsilon_is_zero_without_dp(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    assert trainer.epsilon(delta=1e-5) == 0.0


def test_trainer_epsilon_grows_after_dp_rounds(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer.dp_noise_sigma = 1.0
    trainer.dp_l2_clip = 1.0
    trainer.local_steps = 2
    _ingest_random(trainer)
    eps_before = trainer.epsilon(delta=1e-5)
    trainer.step()
    eps_after = trainer.epsilon(delta=1e-5)
    assert eps_after > eps_before


def test_trainer_higher_sigma_yields_smaller_epsilon(small_mappo: MAPPO) -> None:
    rng_state = torch.random.get_rng_state()

    trainer_low = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer_low.dp_noise_sigma = 0.5
    trainer_low.dp_l2_clip = 1.0
    trainer_low.local_steps = 3
    _ingest_random(trainer_low)
    trainer_low.step()
    eps_low = trainer_low.epsilon(delta=1e-5)

    torch.random.set_rng_state(rng_state)
    trainer_high = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer_high.dp_noise_sigma = 4.0
    trainer_high.dp_l2_clip = 1.0
    trainer_high.local_steps = 3
    _ingest_random(trainer_high)
    trainer_high.step()
    eps_high = trainer_high.epsilon(delta=1e-5)

    assert eps_high < eps_low, f"higher sigma should shrink ε; low={eps_low} high={eps_high}"


# ── per-example clipping & Poisson subsampling ─────────────────────


def test_dp_clipping_is_per_example(small_mappo: MAPPO, monkeypatch: pytest.MonkeyPatch) -> None:
    """A single outlier (gradient ~100× the rest) must NOT dominate the
    DP step. With per-example clipping each sample's gradient is bounded
    by ``dp_l2_clip`` individually before summing, so the weight movement
    on the outlier batch stays within roughly ``lr * batch * clip``
    instead of being driven by the outlier's huge raw norm.
    """
    torch.manual_seed(0)
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=1)
    trainer.dp_noise_sigma = 1e-6  # negligible noise so we measure clipping alone
    trainer.dp_l2_clip = 1.0
    trainer.local_steps = 1
    trainer.local_batch_size = 16
    trainer.local_lr = 0.1

    obs_dim = next(iter(trainer.global_baseline.values())).shape[-1]
    n_actions = next(reversed(trainer.global_baseline.values())).shape[0]
    rng = np.random.default_rng(0)
    agent_id = next(iter(trainer.local_actors))
    # 15 "tame" near-zero samples + 1 extreme outlier obs.
    for _ in range(15):
        trainer.ingest(
            agent_id,
            rng.standard_normal(size=(obs_dim,)).astype(np.float32) * 1e-3,
            label=int(rng.integers(0, n_actions)),
        )
    outlier_obs = np.full((obs_dim,), 1e3, dtype=np.float32)
    trainer.ingest(agent_id, outlier_obs, label=int(rng.integers(0, n_actions)))

    pre = {
        name: p.detach().clone()
        for name, p in trainer.local_actors[agent_id].actor.named_parameters()
    }

    # Force the Poisson subsample to include every sample so the outlier
    # is guaranteed present — verifies clipping, not sampling luck.
    def _full(self: FederatedTrainer, n: int) -> torch.Tensor:
        return torch.arange(n, dtype=torch.long)

    monkeypatch.setattr(FederatedTrainer, "_poisson_subsample_indices", _full)
    trainer._train_local_actor(trainer.local_actors[agent_id])

    post = {
        name: p.detach().clone()
        for name, p in trainer.local_actors[agent_id].actor.named_parameters()
    }
    movement_sq = sum(float((post[k] - pre[k]).pow(2).sum().item()) for k in pre)
    movement = math.sqrt(movement_sq)

    # Per-example bound: ||sum_i g_i|| ≤ batch_n * clip, average grad
    # norm ≤ clip, so weight movement per step ≤ lr * clip * sqrt(P)
    # where P is the parameter count. We give a generous 10× margin.
    n_params = sum(p.numel() for p in trainer.local_actors[agent_id].actor.parameters())
    per_example_ceiling = 10.0 * trainer.local_lr * trainer.dp_l2_clip * math.sqrt(float(n_params))
    assert movement < per_example_ceiling, (
        f"movement {movement:.3f} exceeded per-example ceiling "
        f"{per_example_ceiling:.3f}; outlier likely dominated"
    )


def test_poisson_subsampling_skips_empty_batches(small_mappo: MAPPO) -> None:
    """With a tiny sample rate most local steps draw an empty batch.
    The trainer must not crash, must skip those steps, and must still
    accumulate at least one RDP composition when given enough attempts.
    """
    torch.manual_seed(0)
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=2)
    trainer.dp_noise_sigma = 1.0
    trainer.dp_l2_clip = 1.0
    # Tiny rate: 1/100 → most batches are empty.
    trainer.local_batch_size = 1
    samples_per_agent = 100
    trainer.local_steps = 64
    _ingest_random(trainer, samples_per_agent=samples_per_agent)

    # Should not raise even though many inner iterations sample 0 examples.
    record = trainer.step()
    assert record.n_participants == 2
    # At least one Poisson batch landed non-empty across the whole round.
    assert trainer.rdp_accountant is not None
    assert trainer.rdp_accountant.n_steps >= 1


def test_poisson_subsample_indices_obeys_rate(small_mappo: MAPPO) -> None:
    """Empirical inclusion rate must be within 5σ of the target."""
    torch.manual_seed(0)
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=1)
    trainer.local_batch_size = 5
    n = 1000
    idx = trainer._poisson_subsample_indices(n)
    observed = idx.numel() / n
    p = trainer.local_batch_size / n
    sigma = math.sqrt(p * (1 - p) / n)
    assert abs(observed - p) < 5 * sigma + 1e-3


def test_poisson_subsample_handles_zero_buffer(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=1)
    idx = trainer._poisson_subsample_indices(0)
    assert idx.numel() == 0
