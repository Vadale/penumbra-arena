"""Validate a Penumbra-Bench submission JSON file.

Concept taught: a benchmark with a public submission channel needs
mechanical validation BEFORE human review. A small dependency-free
validator catches the 90% of mistakes (missing tasks, wrong composite
arithmetic, out-of-range scores) that would otherwise burn maintainer
attention. We deliberately avoid pulling in `jsonschema` so the CI job
can run in a freshly-bootstrapped Python without extra installs.

Usage
-----
    uv run python scripts/validate_submission.py state/bench/submissions/foo.json
    uv run python scripts/validate_submission.py path/a.json path/b.json

Exit codes:
    0 — all files valid
    1 — at least one file invalid (errors printed to stderr)
    2 — usage / IO error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final, TypeGuard

ALLOWED_TIERS: Final[frozenset[str]] = frozenset({"tiny", "small", "medium", "large"})
REQUIRED_TASK_IDS: Final[tuple[str, ...]] = ("PA1", "AR1", "MC1", "PB1", "LR1")

# Mirrors penumbra_learning.benchmark._COMPOSITE_WEIGHTS. Duplicated here
# (rather than imported) so the validator stays standalone — installable
# into a CI runner without `uv sync --all-packages` (which pulls torch).
COMPOSITE_WEIGHTS: Final[dict[str, float]] = {
    "PA1": 0.25,
    "AR1": 0.20,
    "MC1": 0.20,
    "PB1": 0.15,
    "LR1": 0.20,
}

COMPOSITE_TOL: Final[float] = 1e-6

# Lower bound for submission_timestamp_ns: 2020-01-01 UTC in epoch ns.
MIN_TIMESTAMP_NS: Final[int] = 1_577_836_800_000_000_000

TOP_LEVEL_REQUIRED: Final[tuple[str, ...]] = (
    "submitter",
    "method",
    "tier",
    "tasks",
    "composite_score",
    "submission_timestamp_ns",
    "penumbra_commit",
    "pytorch_version",
    "hardware",
)

TASK_REQUIRED: Final[tuple[str, ...]] = (
    "task_id",
    "score",
    "metric_values",
    "n_episodes",
    "wall_seconds",
)


class SubmissionValidationError(Exception):
    """A single human-readable validation failure."""


def _is_number(x: object) -> TypeGuard[int | float]:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _validate_top_level(data: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"submission must be a JSON object, got {type(data).__name__}"]
    for key in TOP_LEVEL_REQUIRED:
        if key not in data:
            errors.append(f"missing top-level field: {key!r}")
    return errors


def _validate_scalar_fields(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    submitter = data.get("submitter")
    if not isinstance(submitter, str) or not submitter.strip():
        errors.append("submitter must be a non-empty string")

    method = data.get("method")
    if not isinstance(method, str) or not method.strip():
        errors.append("method must be a non-empty string")

    tier = data.get("tier")
    if tier not in ALLOWED_TIERS:
        errors.append(f"tier {tier!r} not in {sorted(ALLOWED_TIERS)}")

    composite = data.get("composite_score")
    if not _is_number(composite):
        errors.append("composite_score must be a number")
    elif not (0.0 <= float(composite) <= 1.0):
        errors.append(f"composite_score out of [0, 1]: {composite}")

    ts = data.get("submission_timestamp_ns")
    if not isinstance(ts, int) or isinstance(ts, bool):
        errors.append("submission_timestamp_ns must be an integer (epoch ns)")
    elif ts < MIN_TIMESTAMP_NS:
        errors.append(
            f"submission_timestamp_ns={ts} predates 2020-01-01 — likely seconds/ms instead of ns"
        )

    for key in ("penumbra_commit", "pytorch_version", "hardware"):
        v = data.get(key)
        if not isinstance(v, str) or not v.strip():
            errors.append(f"{key} must be a non-empty string")

    return errors


def _validate_task(task: object, index: int) -> list[str]:
    errors: list[str] = []
    if not isinstance(task, dict):
        return [f"tasks[{index}] must be an object, got {type(task).__name__}"]

    for key in TASK_REQUIRED:
        if key not in task:
            errors.append(f"tasks[{index}] missing field: {key!r}")

    task_id = task.get("task_id")
    if task_id not in REQUIRED_TASK_IDS:
        errors.append(f"tasks[{index}].task_id={task_id!r} not in {REQUIRED_TASK_IDS}")

    score = task.get("score")
    if not _is_number(score):
        errors.append(f"tasks[{index}].score must be a number")
    elif not (0.0 <= float(score) <= 1.0):
        errors.append(f"tasks[{index}].score out of [0, 1]: {score}")

    metric_values = task.get("metric_values")
    if not isinstance(metric_values, dict):
        errors.append(f"tasks[{index}].metric_values must be an object")
    else:
        for mk, mv in metric_values.items():
            if not isinstance(mk, str):
                errors.append(f"tasks[{index}].metric_values has non-string key {mk!r}")
            if not _is_number(mv):
                errors.append(
                    f"tasks[{index}].metric_values[{mk!r}] must be a number, got {type(mv).__name__}"
                )

    n_episodes = task.get("n_episodes")
    if not isinstance(n_episodes, int) or isinstance(n_episodes, bool):
        errors.append(f"tasks[{index}].n_episodes must be an integer")
    elif n_episodes < 1:
        errors.append(f"tasks[{index}].n_episodes must be >= 1, got {n_episodes}")

    wall_seconds = task.get("wall_seconds")
    if not _is_number(wall_seconds):
        errors.append(f"tasks[{index}].wall_seconds must be a number")
    elif float(wall_seconds) < 0.0:
        errors.append(f"tasks[{index}].wall_seconds must be >= 0, got {wall_seconds}")

    return errors


def _validate_tasks_array(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return ["tasks must be a JSON array"]

    if len(tasks) != len(REQUIRED_TASK_IDS):
        errors.append(
            f"tasks must contain exactly {len(REQUIRED_TASK_IDS)} entries, got {len(tasks)}"
        )

    for i, task in enumerate(tasks):
        errors.extend(_validate_task(task, i))

    seen: set[str] = set()
    for task in tasks:
        if isinstance(task, dict):
            tid = task.get("task_id")
            if isinstance(tid, str):
                if tid in seen:
                    errors.append(f"duplicate task_id {tid!r}")
                seen.add(tid)
    missing = [t for t in REQUIRED_TASK_IDS if t not in seen]
    if missing:
        errors.append(f"missing required task_id(s): {missing}")

    return errors


def _validate_composite(data: dict[str, Any]) -> list[str]:
    tasks = data.get("tasks")
    composite = data.get("composite_score")
    if not isinstance(tasks, list) or not _is_number(composite):
        return []  # earlier checks already flagged the shape problem

    score_by_id: dict[str, float] = {}
    for task in tasks:
        if isinstance(task, dict):
            tid = task.get("task_id")
            sc = task.get("score")
            if isinstance(tid, str) and _is_number(sc):
                score_by_id[tid] = float(sc)

    if set(score_by_id) != set(COMPOSITE_WEIGHTS):
        return []  # composite is undefined when tasks are incomplete

    expected = sum(COMPOSITE_WEIGHTS[t] * score_by_id[t] for t in COMPOSITE_WEIGHTS)
    delta = abs(expected - float(composite))
    if delta > COMPOSITE_TOL:
        msg = (
            f"composite_score={composite} does not match recomputation "
            f"{expected:.10f} (delta={delta:.3e}, tol={COMPOSITE_TOL})"
        )
        return [msg]
    return []


def validate(data: object) -> list[str]:
    """Return a list of validation errors. Empty list = valid."""
    errors = _validate_top_level(data)
    if errors:
        return errors
    assert isinstance(data, dict)
    errors.extend(_validate_scalar_fields(data))
    errors.extend(_validate_tasks_array(data))
    errors.extend(_validate_composite(data))
    return errors


def validate_file(path: Path) -> list[str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        return [f"cannot read {path}: {e}"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return [f"invalid JSON in {path}: {e}"]
    return validate(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="submission JSON file(s)")
    args = parser.parse_args(argv)

    overall_ok = True
    for path in args.paths:
        errors = validate_file(path)
        if errors:
            overall_ok = False
            print(f"FAIL {path}", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
        else:
            print(f"OK   {path}")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
