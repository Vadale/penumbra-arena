"""YAML-driven lesson runner.

A lesson is a list of steps; each step has:
- `instruction`: human-readable goal
- `validate_cmd`: shell command the runner re-executes to check progress
- `expected_pattern`: regex the output must match
- `hint`: shown if the check fails

Lessons live in `penumbra_shell_coach/lessons/*.yaml`.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class Step:
    instruction: str
    validate_cmd: str
    expected_pattern: str
    hint: str


@dataclass(frozen=True, slots=True)
class Lesson:
    id: str
    title: str
    steps: tuple[Step, ...]
    narrative: str = ""
    prereqs: tuple[str, ...] = ()
    pillars_touched: tuple[str, ...] = ()
    difficulty: str = ""


def list_lessons() -> list[Lesson]:
    """Discover all bundled lessons and return them in id order."""
    package_files = resources.files("penumbra_shell_coach.lessons")
    lessons: list[Lesson] = []
    for entry in package_files.iterdir():
        if not entry.name.endswith(".yaml"):
            continue
        lessons.append(_load_lesson(entry))
    lessons.sort(key=lambda lesson: lesson.id)
    return lessons


def load_lesson(lesson_id: str) -> Lesson:
    """Load a single lesson by its internal `id` field (not the filename)."""
    for lesson in list_lessons():
        if lesson.id == lesson_id:
            return lesson
    raise LessonNotFoundError(f"no lesson with id '{lesson_id}'")


def _load_lesson(path: object) -> Lesson:
    """Parse a lesson YAML file (path-like or importlib.resources entry)."""
    raw = Path(str(path)).read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    return Lesson(
        id=data["id"],
        title=data["title"],
        steps=tuple(
            Step(
                instruction=step["instruction"],
                validate_cmd=step["validate_cmd"],
                expected_pattern=step["expected_pattern"],
                hint=step.get("hint", ""),
            )
            for step in data["steps"]
        ),
        narrative=str(data.get("narrative", "")),
        prereqs=tuple(str(p) for p in data.get("prereqs", []) or []),
        pillars_touched=tuple(str(p) for p in data.get("pillars_touched", []) or []),
        difficulty=str(data.get("difficulty", "")),
    )


@dataclass(frozen=True, slots=True)
class StepResult:
    step_index: int
    succeeded: bool
    output: str
    error: str | None


def check_step(step: Step, *, cwd: str | None = None) -> StepResult:
    """Run `step.validate_cmd` in a shell and check the output regex."""
    try:
        completed = subprocess.run(  # noqa: S602 — validate_cmd comes from bundled YAML
            step.validate_cmd,
            shell=True,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return StepResult(step_index=0, succeeded=False, output="", error="timeout (>10s)")

    output = (completed.stdout or "") + (completed.stderr or "")
    succeeded = bool(re.search(step.expected_pattern, output, flags=re.MULTILINE))
    err = None if completed.returncode == 0 else (completed.stderr or "(no stderr)")
    return StepResult(step_index=0, succeeded=succeeded, output=output, error=err)


def shell_safe(cmd: str) -> bool:
    """Best-effort check that `cmd` doesn't contain obviously destructive ops."""
    tokens = shlex.split(cmd)
    blacklist = {"rm", "shutdown", "reboot", "dd", "mkfs", "diskutil"}
    return not any(t.split("/")[-1] in blacklist for t in tokens)


class LessonNotFoundError(KeyError):
    """Raised when the requested lesson id isn't bundled."""
