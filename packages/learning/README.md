# penumbra-learning — MAPPO + GATv2 + federated DP-SGD

Multi-agent reinforcement learning on Apple Metal (MPS), plus the
federated layer that does **real** local SGD with per-example DP-SGD
clipping + CKKS-encrypted aggregation. This README is the tour of
how the pieces fit and how to use each one alone.

## What you get

### Core RL

| File | Concept |
|---|---|
| `device.py` | Portable device selection (MPS > CUDA > CPU) |
| `env.py` | PettingZoo `ParallelEnv` adapter — K=6 nearest neighbour obs, discrete action over neighbour-index, dense reward = goal-walk progress |
| `mappo.py` | MAPPO from scratch (CleanRL-style): shared actor + centralised critic, PPO clip + GAE + grad clipping |
| `gat_pathfinder.py` | GATv2 pathfinder *from scratch* (no PyTorch Geometric dep) |
| `supply_gnn.py` | PyG `GATv2Conv` over the supply graph (uses torch-geometric ≥2.6) |
| `policy_loader.py` | `MappoRuntime` — shared actor for the live arena AND the background trainer |
| `live_trainer.py` | `LiveTrainer` — background asyncio task that runs PPO updates against the SAME `agent_net` the inference path serves from |

### Federated learning

| File | Concept |
|---|---|
| `federated.py` | REAL local SGD with per-agent (obs, greedy-label) buffers; per-example DP-SGD clipping via `torch.func.vmap(grad(functional_call))`; Poisson subsampling; CKKS encrypted aggregation; Krum + TrimmedMean Byzantine-robust aggregators; FedProx proximal term; per-client personalisation heads; top-k sparsification + 8-bit quantization |
| `federated_dp.py` | Rényi DP accountant for the Sampled Gaussian Mechanism — 118-order grid (denser than legacy 12), Canonne-Kamath-Steinke RDP→DP bound |
| `logistics_shaper.py` | Reward shaping for the logistics task (dispatch bonus/penalty, fill-rate bonus) |

### Benchmark

| File | Concept |
|---|---|
| `benchmark.py` | Penumbra-Bench score aggregation (5 tasks, 4 difficulty tiers) |

## How to use it

### Boot MAPPO + interact

```python
from penumbra_learning.mappo import MAPPO, MAPPOConfig

cfg = MAPPOConfig(obs_dim=18, n_actions=7, n_agents=50, hidden=128)
agent = MAPPO(cfg)

# Inference one step per agent on a (n_agents, obs_dim) tensor:
import torch
obs = torch.randn(cfg.n_agents, cfg.obs_dim)
actions = agent.select_actions(obs, temperature=1.0)
```

The live arena loads a checkpoint (`PENUMBRA_MAPPO_CHECKPOINT`) and
serves inference from the same `agent_net` the `LiveTrainer` writes to.
Toggle MAPPO/RANDOM in the dashboard status bar to switch the live
policy without restart.

### Federated DP-SGD round

```python
from penumbra_learning.federated import FederatedTrainer
from penumbra_learning.mappo import MAPPO, MAPPOConfig

mappo = MAPPO(MAPPOConfig(obs_dim=18, n_actions=7, n_agents=50, hidden=16))
trainer = FederatedTrainer.from_mappo(mappo, n_agents=10)

# Each agent ingests (observation, greedy-label) pairs.
for agent_id, obs, label in stream_of_local_data():
    trainer.ingest(agent_id, obs, label)

# Configure DP-SGD.
trainer.dp_noise_sigma = 1.0
trainer.dp_l2_clip = 1.0

# Run one round. `method` picks the aggregation rule.
trainer.step(method="krum")  # or "fedavg", "trimmed_mean", "ckks_sum"

# Check the accumulated privacy spend.
print(trainer.epsilon(delta=1e-5))
```

The per-example clipping uses `torch.func.vmap(grad(functional_call))`
on each sample BEFORE summing + adding Gaussian noise — that's what
makes the (ε, δ) numbers actual DP-SGD guarantees per Abadi 2016
rather than the loose "clip the aggregate" approximation.

### Rényi DP accountant standalone

```python
from penumbra_learning.federated_dp import RDPAccountant

acc = RDPAccountant()  # 118-order grid
for _ in range(1000):
    acc.step(noise_multiplier=1.1, sample_rate=0.01)
print(acc.epsilon(target_delta=1e-5))
```

`examples/05_rdp_dp_sgd_accountant.py` shows the dense-vs-sparse
comparison numerically.

### Live trainer + reward shaping

```python
from penumbra_learning.live_trainer import build_live_trainer

trainer = build_live_trainer(mappo_runtime=runtime, env=penumbra_env)
await trainer.start()  # one PPO iteration at a time, asynchronously
# ... mutate the reward weights live:
trainer.env.reward_weights.dispatch_bonus = 12.0
# ... next iteration picks up the new weights.
await trainer.stop()
```

The reward shaping sliders in the dashboard's `RewardShapingChart.tsx`
mutate the shared `RewardWeights` singleton; the trainer reads it on
its next iteration without restart.

## Why this is more than a CleanRL fork

CleanRL is the canonical "small + readable RL" reference. Penumbra's
learning package extends it in three ways:

1. **Live training that mutates the inference policy.** Most RL setups
   train OR infer; we do both against the same `agent_net` pointer.
2. **Per-example DP-SGD via `torch.func.vmap(grad(...))`.** Most
   educational FL repos clip the aggregated gradient (which doesn't
   give the per-example sensitivity bound Abadi 2016 needs). We
   shipped the correct version + a regression test.
3. **CKKS-encrypted aggregation that actually decrypts to the right
   number.** Not a stub — uses TenSEAL with real slot batching, ~4096
   slots/ciphertext. Encrypt ten 50-d deltas, decrypt the sum, get
   FedAvg back.

These three together are the differentiator vs the "FL hello world"
genre.

## Test sentinels

The test file `tests/test_federated_dp.py` contains regression tests
for the audit-closed properties:

- `test_dp_clipping_is_per_example` — pins `vmap(grad(...))` shape.
- `test_poisson_subsampling_skips_empty_batches` — Bernoulli inclusion,
  not random-with-replacement.
- `test_default_grid_is_denser_than_sparse_baseline` — 118 ≥ ~60
  orders gives a tighter ε.

If you fork this, keep these tests — they prevent silent regression
on properties the README of any spin-off DP-SGD library would advertise.

## Extracting this package as a spin-off

The cleanest extraction target is `federated_dp.py` (the Rényi
accountant). It depends only on the Python stdlib + numpy and could
ship as `penumbra-rdp-accountant` (~500 LOC pip package). Audience:
researchers who want a clean, reviewed Rényi accountant with a dense
order grid, without dragging in the full Opacus framework.

If you wanted to do this:

1. Copy `packages/learning/penumbra_learning/federated_dp.py` to a new
   repo.
2. Add `tests/test_federated_dp.py` (the parts that test the accountant
   in isolation, not the FederatedTrainer integration ones).
3. Write a 1-page README explaining the SGM RDP analysis at a high
   level + the dense-grid argument.
4. Publish.

Expected work: 1-2 days.

Extracting `federated.py` itself (the full DP-SGD trainer) is harder
because it depends on the MAPPO actor shape. A spin-off "drop-in
DP-SGD for any pytorch model" would take ~2 weeks of API work.

## Layout

```
penumbra_learning/
  device.py
  env.py
  mappo.py
  gat_pathfinder.py
  supply_gnn.py
  policy_loader.py
  live_trainer.py
  federated.py
  federated_dp.py
  logistics_shaper.py
  benchmark.py
```
