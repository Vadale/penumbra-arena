"""Tests for scripts/validate_submission.py.

Concept taught: a CI gatekeeper script must itself be tested. We cover
the four failure modes contributors actually hit (missing task, wrong
composite, out-of-range score, malformed submitter) plus the happy path.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_submission.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_submission", VALIDATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_submission"] = module
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


def _valid_submission() -> dict[str, Any]:
    scores = {"PA1": 0.4, "AR1": 0.5, "MC1": 0.6, "PB1": 0.3, "LR1": 0.7}
    composite = sum(validator.COMPOSITE_WEIGHTS[t] * s for t, s in scores.items())
    return {
        "submitter": "test-user",
        "method": "unit-test-policy",
        "tier": "tiny",
        "tasks": [
            {
                "task_id": tid,
                "score": scores[tid],
                "metric_values": {"primary": scores[tid]},
                "n_episodes": 20,
                "wall_seconds": 1.23,
            }
            for tid in ("PA1", "AR1", "MC1", "PB1", "LR1")
        ],
        "composite_score": composite,
        "submission_timestamp_ns": 1_779_530_743_055_576_000,
        "penumbra_commit": "deadbeefcafebabe",
        "pytorch_version": "2.12.0",
        "hardware": "Darwin arm64",
    }


@pytest.fixture
def submission_file(tmp_path: Path) -> Path:
    return tmp_path / "submission.json"


def _write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2))


def test_valid_submission_passes(submission_file: Path) -> None:
    _write(submission_file, _valid_submission())
    assert validator.validate_file(submission_file) == []
    assert validator.main([str(submission_file)]) == 0


def test_missing_task_fails(submission_file: Path) -> None:
    data = _valid_submission()
    data["tasks"] = [t for t in data["tasks"] if t["task_id"] != "LR1"]
    _write(submission_file, data)
    errors = validator.validate_file(submission_file)
    assert errors
    assert any("LR1" in e or "exactly 5" in e for e in errors)
    assert validator.main([str(submission_file)]) == 1


def test_wrong_composite_fails(submission_file: Path) -> None:
    data = _valid_submission()
    data["composite_score"] = data["composite_score"] + 0.1
    _write(submission_file, data)
    errors = validator.validate_file(submission_file)
    assert errors
    assert any("composite_score" in e and "match recomputation" in e for e in errors)


def test_out_of_range_score_fails(submission_file: Path) -> None:
    data = _valid_submission()
    data["tasks"][0]["score"] = 1.5
    # Recompute composite so we isolate the score-range error.
    score_by_id = {t["task_id"]: t["score"] for t in data["tasks"]}
    data["composite_score"] = sum(
        validator.COMPOSITE_WEIGHTS[t] * s for t, s in score_by_id.items()
    )
    _write(submission_file, data)
    errors = validator.validate_file(submission_file)
    assert errors
    assert any("score out of [0, 1]" in e for e in errors)


def test_empty_submitter_fails(submission_file: Path) -> None:
    data = _valid_submission()
    data["submitter"] = "   "
    _write(submission_file, data)
    errors = validator.validate_file(submission_file)
    assert any("submitter" in e for e in errors)


def test_bad_tier_fails(submission_file: Path) -> None:
    data = _valid_submission()
    data["tier"] = "humongous"
    _write(submission_file, data)
    errors = validator.validate_file(submission_file)
    assert any("tier" in e for e in errors)


def test_timestamp_in_seconds_fails(submission_file: Path) -> None:
    data = _valid_submission()
    data["submission_timestamp_ns"] = 1_700_000_000  # seconds, not ns
    _write(submission_file, data)
    errors = validator.validate_file(submission_file)
    assert any("submission_timestamp_ns" in e for e in errors)


def test_duplicate_task_fails(submission_file: Path) -> None:
    data = _valid_submission()
    data["tasks"][1] = copy.deepcopy(data["tasks"][0])
    _write(submission_file, data)
    errors = validator.validate_file(submission_file)
    assert any("duplicate task_id" in e or "missing required task_id" in e for e in errors)


def test_malformed_json_fails(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not valid json")
    errors = validator.validate_file(path)
    assert errors
    assert any("invalid JSON" in e for e in errors)


def test_missing_top_level_field_fails(submission_file: Path) -> None:
    data = _valid_submission()
    del data["hardware"]
    _write(submission_file, data)
    errors = validator.validate_file(submission_file)
    assert any("hardware" in e for e in errors)


def test_shipped_baseline_submission_passes() -> None:
    """The baseline submissions checked into state/bench/ must validate.

    They are the reference output of run_benchmark; if they stop
    validating, either the benchmark dataclass or the validator drifted.
    """
    baseline = REPO_ROOT / "state" / "bench" / "mappo-v0-tiny.json"
    if not baseline.is_file():
        pytest.skip(f"baseline not present: {baseline}")
    assert validator.validate_file(baseline) == []
