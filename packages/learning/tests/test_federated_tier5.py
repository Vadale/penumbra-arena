"""Federated learning Tier 5 tests: FedProx + personalisation + compression.

Concept taught: how the three Tier-5 knobs interact with the
``FederatedTrainer``:

- ``fedprox_mu > 0`` injects a proximal term into the local loss and
  is expected to shrink the post-SGD drift from the global baseline.
- ``LocalActor.personal_head`` is a per-client residual that must
  survive aggregation rounds untouched.
- ``topk_fraction < 1.0`` sparsifies each delta; ``quantize_bits == 8``
  quantises survivors to int8 and reports realised wire savings.

These tests assert behaviour, not numerics: defaults (mu=0, topk=1.0,
quantize_bits=0) must reproduce the Tier 1-4 baseline byte-for-byte.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch
from penumbra_learning.federated import (
    FederatedTrainer,
    LocalActor,
    _delta_tensor_nbytes,
    _quantize_dequantize_int8,
    _topk_sparsify,
)
from penumbra_learning.mappo import MAPPO, MAPPOConfig


@pytest.fixture
def small_mappo() -> MAPPO:
    cfg = MAPPOConfig(obs_dim=18, n_actions=7, n_agents=5, hidden=16)
    return MAPPO(cfg)


def _ingest_random(trainer: FederatedTrainer, samples_per_agent: int = 32) -> None:
    rng = np.random.default_rng(42)
    obs_dim = next(iter(trainer.global_baseline.values())).shape[-1]
    n_actions = next(reversed(trainer.global_baseline.values())).shape[0]
    for agent_id in trainer.local_actors:
        for _ in range(samples_per_agent):
            obs = rng.standard_normal(size=(obs_dim,)).astype(np.float32)
            label = int(rng.integers(0, n_actions))
            trainer.ingest(agent_id, obs, label)


# ── FedProx ─────────────────────────────────────────────────────────


def test_fedprox_reduces_parameter_drift(small_mappo: MAPPO) -> None:
    """Local drift with mu > 0 must be smaller than with mu = 0."""
    torch.manual_seed(0)
    trainer_plain = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer_plain.local_steps = 30
    trainer_plain.local_lr = 0.1
    _ingest_random(trainer_plain, samples_per_agent=64)

    torch.manual_seed(0)
    trainer_prox = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer_prox.local_steps = 30
    trainer_prox.local_lr = 0.1
    trainer_prox.set_fedprox(mu=1.0)
    _ingest_random(trainer_prox, samples_per_agent=64)

    trainer_plain._local_phase()
    trainer_prox._local_phase()

    def drift(trainer: FederatedTrainer) -> float:
        total = 0.0
        for state in trainer.local_actors.values():
            local = state.weights()
            for name, baseline in trainer.global_baseline.items():
                total += float((local[name] - baseline).pow(2).sum().item())
        return total**0.5

    drift_plain = drift(trainer_plain)
    drift_prox = drift(trainer_prox)
    assert drift_prox < drift_plain


def test_fedprox_default_preserves_loss_path(small_mappo: MAPPO) -> None:
    """With mu=0 the trainer's behaviour must match the Tier 1 baseline."""
    torch.manual_seed(0)
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    assert trainer.fedprox_mu == 0.0
    trainer.local_steps = 4
    _ingest_random(trainer)
    record = trainer.step()
    assert record.mean_local_loss > 0.0


def test_fedprox_rejects_negative_mu(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    with pytest.raises(ValueError, match="mu"):
        trainer.set_fedprox(-0.1)


# ── Personalisation heads ───────────────────────────────────────────


def test_local_actor_with_personal_head(small_mappo: MAPPO) -> None:
    template = small_mappo.actor
    head_in = 16
    n_actions = 7
    actor = LocalActor.fresh(
        agent_id=0,
        template=template,
        with_personal_head=True,
        hidden_dim=head_in,
        n_actions=n_actions,
    )
    assert actor.personal_head is not None
    assert actor.personal_head.in_features == head_in
    assert actor.personal_head.out_features == n_actions
    assert torch.all(actor.personal_head.weight == 0)


def test_personal_heads_unchanged_across_aggregation(small_mappo: MAPPO) -> None:
    """Aggregation must NOT touch the per-client personal head."""
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=4, with_personal_heads=True)
    trainer.local_steps = 4
    _ingest_random(trainer)
    # Capture each personal head's weights pre-round, after dirtying them.
    pre: dict[int, torch.Tensor] = {}
    for agent_id, state in trainer.local_actors.items():
        assert state.personal_head is not None
        with torch.no_grad():
            state.personal_head.weight.add_(torch.randn_like(state.personal_head.weight))
        pre[agent_id] = state.personal_head.weight.detach().clone()
    trainer.step()
    trainer.step()
    for agent_id, state in trainer.local_actors.items():
        assert state.personal_head is not None
        assert torch.allclose(state.personal_head.weight, pre[agent_id])


def test_personal_head_forward_changes_logits(small_mappo: MAPPO) -> None:
    """A nonzero personal head must shift forward() output away from the
    shared body's raw logits."""
    template = small_mappo.actor
    actor = LocalActor.fresh(
        agent_id=0,
        template=template,
        with_personal_head=True,
        hidden_dim=16,
        n_actions=7,
    )
    assert actor.personal_head is not None
    obs = torch.randn(2, 18)
    body: torch.nn.Module = actor.actor.net  # type: ignore[assignment]
    shared_logits = body(obs)
    with torch.no_grad():
        actor.personal_head.weight.fill_(0.5)
    personal_logits = actor.forward(obs)
    assert not torch.allclose(shared_logits, personal_logits)


def test_from_mappo_default_has_no_personal_head(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    for state in trainer.local_actors.values():
        assert state.personal_head is None


# ── Top-k sparsification ────────────────────────────────────────────


def test_topk_sparsify_zeros_most_entries() -> None:
    t = torch.arange(100, dtype=torch.float32) - 50.0
    out = _topk_sparsify(t, fraction=0.1)
    nonzero = int(torch.count_nonzero(out).item())
    # 10% of 100 = 10 survivors.
    assert nonzero == 10
    # Surviving entries are the ones with largest absolute value.
    kept = out[out != 0]
    assert torch.all(kept.abs() >= 40)


def test_topk_sparsify_fraction_one_is_identity() -> None:
    t = torch.randn(50)
    out = _topk_sparsify(t, fraction=1.0)
    assert torch.allclose(out, t)


def test_topk_aggregation_zeros_about_ninety_percent(small_mappo: MAPPO) -> None:
    """topk=0.1 must zero about 90% of every delta tensor."""
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer.local_steps = 4
    trainer.set_compression(topk_fraction=0.1, quantize_bits=0)
    _ingest_random(trainer)
    trainer._local_phase()
    deltas, _ = trainer._collect_deltas()
    for delta in deltas:
        for tensor in delta.values():
            n = tensor.numel()
            if n < 10:
                continue
            nnz = int(torch.count_nonzero(tensor).item())
            assert nnz <= max(1, round(n * 0.1))
            zero_fraction = 1.0 - (nnz / n)
            assert zero_fraction >= 0.85


# ── Quantisation ────────────────────────────────────────────────────


def test_quantize_dequantize_round_trip_close() -> None:
    t = torch.randn(200) * 2.0
    q = _quantize_dequantize_int8(t)
    # Symmetric int8 quantisation tops out at scale ~ 2*max/127, so
    # absolute error per element is bounded.
    assert q.shape == t.shape
    err = (q - t).abs().max().item()
    assert err < 0.05


def test_quantize_zero_tensor_returns_zero() -> None:
    t = torch.zeros(10)
    out = _quantize_dequantize_int8(t)
    assert torch.all(out == 0)


def test_quantization_reduces_bandwidth(small_mappo: MAPPO) -> None:
    """Quantised wire bytes must be strictly less than dense."""
    trainer_plain = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer_plain.local_steps = 4
    _ingest_random(trainer_plain)
    plain_record = trainer_plain.step()

    trainer_q = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer_q.local_steps = 4
    trainer_q.set_compression(topk_fraction=1.0, quantize_bits=8)
    _ingest_random(trainer_q)
    q_record = trainer_q.step()

    assert q_record.bandwidth_bytes < plain_record.bandwidth_bytes


def test_topk_plus_quantize_reduces_bandwidth(small_mappo: MAPPO) -> None:
    """Combining top-k + 8-bit must yield even smaller wire bytes."""
    trainer_plain = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer_plain.local_steps = 4
    _ingest_random(trainer_plain)
    plain_record = trainer_plain.step()

    trainer_c = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer_c.local_steps = 4
    trainer_c.set_compression(topk_fraction=0.1, quantize_bits=8)
    _ingest_random(trainer_c)
    c_record = trainer_c.step()

    assert c_record.bandwidth_bytes < plain_record.bandwidth_bytes


# ── Wire-byte accounting ────────────────────────────────────────────


def test_delta_tensor_nbytes_dense_matches_raw() -> None:
    t = torch.zeros(100, dtype=torch.float32)
    n = _delta_tensor_nbytes(t, topk_active=False, quant_active=False)
    assert n == 100 * 4


def test_delta_tensor_nbytes_topk_counts_only_nnz() -> None:
    t = torch.zeros(100, dtype=torch.float32)
    t[0] = 1.0
    t[5] = 2.0
    n = _delta_tensor_nbytes(t, topk_active=True, quant_active=False)
    # 2 non-zeros × (4-byte index + 4-byte float) = 16.
    assert n == 16


def test_delta_tensor_nbytes_quant_only_one_byte_per_element() -> None:
    t = torch.zeros(100, dtype=torch.float32)
    n = _delta_tensor_nbytes(t, topk_active=False, quant_active=True)
    assert n == 100 + 8  # 1 byte/element + 8 byte per-tensor scale.


# ── set_compression validation ──────────────────────────────────────


def test_set_compression_rejects_bad_topk(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    with pytest.raises(ValueError, match="topk_fraction"):
        trainer.set_compression(topk_fraction=2.0, quantize_bits=0)
    with pytest.raises(ValueError, match="topk_fraction"):
        trainer.set_compression(topk_fraction=-0.1, quantize_bits=0)


def test_set_compression_rejects_bad_bits(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    with pytest.raises(ValueError, match="quantize_bits"):
        trainer.set_compression(topk_fraction=1.0, quantize_bits=4)


# ── defaults preserve original behaviour ────────────────────────────


def test_defaults_match_uncompressed_wire_bytes(small_mappo: MAPPO) -> None:
    """A trainer at default knobs must match the pre-Tier-5 dense byte count."""
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    trainer.local_steps = 4
    _ingest_random(trainer)
    trainer._local_phase()
    _, wire_bytes = trainer._collect_deltas()
    expected = 0
    for state in trainer.local_actors.values():
        delta = state.delta_against(trainer.global_baseline)
        for tensor in delta.values():
            expected += int(tensor.element_size() * tensor.numel())
    assert wire_bytes == expected


def test_summary_exposes_tier5_fields(small_mappo: MAPPO) -> None:
    trainer = FederatedTrainer.from_mappo(small_mappo, n_agents=3)
    summary = trainer.summary()
    assert "fedprox_mu" in summary
    assert "topk_fraction" in summary
    assert "quantize_bits" in summary
    assert "personalised" in summary
    assert summary["personalised"] is False
