# penumbra-learning

Multi-agent reinforcement learning on Apple MPS.

## Concept taught

- `env.py` — PettingZoo `ParallelEnv` that wraps `penumbra_core.Simulation`. One step per simulation tick; observations are local neighbour-cost vectors plus a goal-distance feature.
- `mappo.py` — MAPPO (CleanRL-style). Centralised critic, decentralised actors. Two-layer MLP, hidden 128, runs on `mps` with a CPU-fallback path.
- `gat_pathfinder.py` — GATv2 (PyTorch Geometric) that estimates node-to-goal distances given current edge costs. Used as a feature for the actor.
- `training.py` — self-play loop with checkpoint save/load.

## M4 budget

Actor + critic ≤ 2-layer MLP, hidden 128, ~80KB each. GAT ≤ 64-dim embeddings. All on `torch.device("mps")` with float32. Total RSS contribution: <2.5 GB.
