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
from penumbra_learning.env import PenumbraEnv, NEIGHBOURS_K, OBS_PER_NEIGHBOUR
from penumbra_learning.mappo import MAPPO, MAPPOConfig
from penumbra_learning.gat_pathfinder import GATv2Layer, GATv2Pathfinder
from penumbra_learning.training import train, TrainingConfig
```

## M4 budget

Actor + critic: 2-layer MLPs, hidden 128 ≈ 80 KB each. GATv2: ≤64-dim
embeddings. Total resident under MPS: <2.5 GB while training, <50 MB
for inference only.
