# penumbra-learning

Multi-agent reinforcement learning + graph attention, running on
Apple Metal (MPS).

## Concept taught

- **`device.py`** — portable device selection. MPS > CUDA > CPU.
- **`env.py`** — adapting a domain simulation to the PettingZoo
  `ParallelEnv` interface. K=6 nearest-neighbour observations,
  Discrete(K+1) actions (K hops + explicit "stay"), reward shaping
  with per-tick penalty, illegal-move penalty, and goal-reaching bonus.
- **`mappo.py`** — Multi-Agent PPO (CleanRL-style). *Centralised
  training, decentralised execution*: a centralised critic sees the
  global observation during training; at deployment only the actor
  (shared across agents) is needed. Concept that the user *should*
  walk through: PPO's clipped surrogate objective and Generalised
  Advantage Estimation (GAE).
- **`gat_pathfinder.py`** — GATv2 (Brody, Alon, Yahav 2022) from
  scratch, no PyTorch Geometric dependency. Two-layer attention with
  a learnable edge-cost weight. The from-scratch version is the
  pedagogical asset: read the forward() and the attention math is
  literally visible in 25 lines.
- **`training.py`** — self-play rollout + GAE + PPO update + checkpoint.
- **`policy_loader.py`** — `mappo_batch_policy()` returns the inference
  policy plus a mutable `MappoRuntime` (temperature, deterministic,
  enabled, last_actions) the dashboard reaches into to flip behaviour
  at runtime without restarting the server.
- **`live_trainer.py`** — background `LiveTrainer` that owns an
  internal `PenumbraEnv` and runs ONE PPO iteration at a time against
  the live actor. The user toggles start/stop from the dashboard and
  watches actor/critic/entropy/reward curves update every ~1.5s.

### Phase 2.5 additions (federated + logistics-coupling)

- **`federated.py`** — `FederatedTrainer` w/ real local SGD on per-
  agent (obs, label) buffers. Aggregators: `fedavg`, `ckks_sum` (real
  CKKS encrypt-sum-decrypt via the project's CKKS backend, with slot
  batching for actors larger than `slot_count`), `krum` (Blanchard
  et al. 2017 Byzantine-robust selection), `trimmed_mean` (per-
  coordinate). FedProx proximal term, per-client personalisation
  heads, top-k sparsification + 8-bit quantisation. `Concept taught:`
  the SGD math is the same locally and federally — what changes is
  who sees which gradient at which step.
- **`federated_dp.py`** — `RDPAccountant` for Sampled Gaussian
  Mechanism (Mironov-Talwar-Zhang 2019), closed-form Rényi DP
  composition, conversion to (ε, δ)-DP via Canonne-Kamath-Steinke
  2020 bound. `Concept taught:` Rényi DP is the right composition
  framework for SGD-style mechanisms; the toy `clip/sigma` accountant
  is unsound — this module replaces it.
- **`logistics_shaper.py`** — `LogisticsRewardShaper` that adds
  dispatch-bonus / dispatch-penalty / fill-rate-bonus terms to the
  per-agent reward, reading from the orchestrator's
  `LogisticsMempool` + `DemandModel`. `Concept taught:` reward
  shaping for sparse-reward multi-agent RL: aligning incentives so
  policies learn to be good carriers, not just goal-seekers.
- **`supply_gnn.py`** — `SupplyGraphEncoder` using PyG GATv2Conv.
  Hidden dim clamped to [8, 64] to stay within the M4 budget.
  `Concept taught:` GNN encoders for spatial-relational state on
  supply graphs — agents that "see" the graph structure can route
  better than agents seeing only local neighbours.
- **`benchmark.py`** — Penumbra-Bench 5-task suite (PA1/AR1/MC1/PB1/
  LR1), `BenchSubmission` dataclass, composite weights, `run_benchmark`
  entry-point used by `scripts/run_benchmark.py` and
  `scripts/generate_baselines.py`.

## Micro-experiments

1. Train a small policy and watch losses converge:
   ```sh
   uv run python scripts/train_initial_checkpoint.py
   ```
   ~30 seconds on M4 MPS for 20 iterations × 128-tick rollouts.
2. Compare GATv2 attention against vanilla GCN (homework):
   in `gat_pathfinder.py`, replace the attention layer with a plain
   `Linear(in_dim, out_dim) + mean over neighbours` aggregator and
   re-run the same pathfinder task. See how the attention head's
   max-selectivity matters when the goal is "pick the cheapest hop".

## Public API

```python
from penumbra_learning.device import best_device
from penumbra_learning.env import (
    PenumbraEnv, NEIGHBOURS_K, OBS_PER_NEIGHBOUR, REWARD_WEIGHTS
)
from penumbra_learning.mappo import MAPPO, MAPPOConfig  # action_probabilities, value_estimate
from penumbra_learning.gat_pathfinder import GATv2Layer, GATv2Pathfinder  # forward_with_attention
from penumbra_learning.training import train, TrainingConfig
from penumbra_learning.policy_loader import mappo_batch_policy, MappoRuntime
from penumbra_learning.live_trainer import LiveTrainer, build_live_trainer, TrainingSample
```

## M4 budget

Actor + critic: 2-layer MLPs, hidden 128 ≈ 80 KB each. GATv2: ≤64-dim
embeddings. Total resident under MPS: <2.5 GB while training, <50 MB
for inference only.
