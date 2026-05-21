"""Train a small MAPPO checkpoint shippable with the repo.

Run once after cloning if you want a non-random policy on first boot:
    uv run python scripts/train_initial_checkpoint.py

Produces `checkpoints/mappo_v0.pt` (~240 KB).
"""

from __future__ import annotations

from penumbra_learning.env import PenumbraEnv
from penumbra_learning.training import TrainingConfig, train


def main() -> None:
    # Match the runtime config (penumbra_core.SimulationConfig) so the
    # critic dim aligns: production runs at n_agents=50, arena_nodes=50.
    env = PenumbraEnv(n_agents=50, arena_nodes=50, max_match_ticks=120, seed=42)
    agent = train(
        env,
        TrainingConfig(
            n_iterations=80,
            rollout_length=128,
            checkpoint_path="checkpoints/mappo_v0.pt",
        ),
    )
    print(f"trained MAPPO on {agent.device}; checkpoint at checkpoints/mappo_v0.pt")


if __name__ == "__main__":
    main()
