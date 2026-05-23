"""Run a policy through Penumbra-Bench at the selected tier.

Usage
-----
    uv run python scripts/run_benchmark.py \\
        --policy checkpoints/mappo_v0.pt \\
        --tier tiny \\
        --submitter Vadale \\
        --method mappo-v0 \\
        --output state/bench/mappo-v0-tiny.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from penumbra_learning.benchmark import run_benchmark, save_submission


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy",
        type=Path,
        default=None,
        help="path to a MAPPO checkpoint; omit for random-walk baseline",
    )
    parser.add_argument("--tier", choices=["tiny", "small", "medium", "large"], default="tiny")
    parser.add_argument("--submitter", default="anonymous")
    parser.add_argument("--method", default="untitled")
    parser.add_argument("--output", type=Path, default=Path("state/bench/submission.json"))
    args = parser.parse_args()

    submission = run_benchmark(
        policy_path=args.policy,
        tier=args.tier,
        submitter=args.submitter,
        method=args.method,
    )
    save_submission(submission, args.output)

    print(f"Penumbra-Bench submission for {submission.method} @ tier={submission.tier}")
    print(f"  composite_score: {submission.composite_score:.4f}")
    for t in submission.tasks:
        print(f"    {t.task_id}: score={t.score:.4f}  ({t.wall_seconds:.1f}s)")
    print(f"  output: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
