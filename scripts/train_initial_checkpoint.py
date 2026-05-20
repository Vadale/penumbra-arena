"""Train a small MAPPO checkpoint shippable with the repo.

Run once after cloning if you want a non-random policy on first boot:
    uv run python scripts/train_initial_checkpoint.py

Produces `checkpoints/mappo_v0.pt` (~240 KB).
"""

from __future__ import annotations

from penumbra_learning.env import PenumbraEnv
from penumbra_learning.training import TrainingConfig, train


def main() -> None:
    env = PenumbraEnv(n_agents=10, arena_nodes=20, max_match_ticks=80, seed=42)
    agent = train(
        env,
        TrainingConfig(
            n_iterations=20,
            rollout_length=128,
            checkpoint_path="checkpoints/mappo_v0.pt",
        ),
    )
    print(f"trained MAPPO on {agent.device}; checkpoint at checkpoints/mappo_v0.pt")


if __name__ == "__main__":
    main()
