"""Penumbra Capture-the-Flag harness.

Concept taught: a CTF is a teaching artifact whose YAML spec OWNS the
truth of what counts as a winning attack. The harness only needs to
load challenges from disk, compare a submitted flag (string equality
or templated hash) against the expected flag for the scenario, and
maintain a per-challenge leaderboard. The hard work — implementing the
attack — is the player's; we give them the scaffolding plus the score.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CHALLENGES_DIR = Path(__file__).resolve().parent.parent / "challenges"


class CTFError(Exception):
    """Base class for CTF errors."""


class ChallengeNotFoundError(CTFError):
    """Requested challenge id is not loaded."""


@dataclass(frozen=True, slots=True)
class Challenge:
    """One CTF challenge spec loaded from YAML."""

    id: str
    title: str
    setup: dict[str, Any]
    acceptance: dict[str, Any]
    flag_template: str

    def expected_flag(self) -> str:
        """Resolve the template. `{{salt_hash}}` ⇒ hex of sha256(id||setup)."""
        salt = self.id + repr(sorted(self.setup.items()))
        digest = hashlib.sha256(salt.encode("utf-8")).hexdigest()[:16]
        return self.flag_template.replace("{{salt_hash}}", digest).replace(
            "{{position_hash}}", digest
        )


@dataclass(slots=True)
class Submission:
    """One leaderboard entry."""

    session_id: str
    submitted_at: float
    correct: bool


@dataclass(slots=True)
class CTFRegistry:
    """In-memory registry of challenges + per-id leaderboards."""

    challenges: dict[str, Challenge] = field(default_factory=dict)
    submissions: dict[str, list[Submission]] = field(default_factory=dict)

    def load_dir(self, directory: Path | None = None) -> int:
        """Load every *.yaml under `directory` (default: challenges/)."""
        root = directory or CHALLENGES_DIR
        if not root.is_dir():
            return 0
        loaded = 0
        for path in sorted(root.glob("*.yaml")):
            spec = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(spec, dict) or "id" not in spec:
                continue
            challenge = Challenge(
                id=str(spec["id"]),
                title=str(spec.get("title", spec["id"])),
                setup=dict(spec.get("setup", {})),
                acceptance=dict(spec.get("acceptance", {})),
                flag_template=str(spec.get("flag_template", "PEN{{{{salt_hash}}}}")),
            )
            self.challenges[challenge.id] = challenge
            loaded += 1
        return loaded

    def list_summaries(self) -> list[dict[str, Any]]:
        """Public summary for /ctf/challenges."""
        return [
            {
                "id": c.id,
                "title": c.title,
                "setup": c.setup,
                "acceptance": c.acceptance,
                "solvers": sum(1 for s in self.submissions.get(c.id, []) if s.correct),
            }
            for c in self.challenges.values()
        ]

    def submit(self, challenge_id: str, flag: str, session_id: str) -> dict[str, Any]:
        """Validate `flag` against the expected flag; record the submission."""
        challenge = self.challenges.get(challenge_id)
        if challenge is None:
            raise ChallengeNotFoundError(f"unknown challenge id {challenge_id!r}")
        expected = challenge.expected_flag()
        correct = flag.strip() == expected
        entry = Submission(session_id=session_id, submitted_at=time.time(), correct=correct)
        self.submissions.setdefault(challenge_id, []).append(entry)
        return {
            "challenge_id": challenge_id,
            "correct": correct,
            "session_id": session_id,
            "submitted_at": entry.submitted_at,
            "expected_flag_prefix": expected[:4] + "…" if not correct else expected,
        }

    def leaderboard(self, challenge_id: str) -> list[dict[str, Any]]:
        """First-correct-submission per session for `challenge_id`."""
        if challenge_id not in self.challenges:
            raise ChallengeNotFoundError(f"unknown challenge id {challenge_id!r}")
        seen: dict[str, Submission] = {}
        for s in self.submissions.get(challenge_id, []):
            if s.correct and s.session_id not in seen:
                seen[s.session_id] = s
        ordered = sorted(seen.values(), key=lambda s: s.submitted_at)
        return [
            {"rank": i + 1, "session_id": s.session_id, "submitted_at": s.submitted_at}
            for i, s in enumerate(ordered)
        ]


_GLOBAL = CTFRegistry()
_GLOBAL.load_dir()


def global_registry() -> CTFRegistry:
    """Process-wide registry used by the FastAPI endpoints."""
    return _GLOBAL


__all__ = [
    "CHALLENGES_DIR",
    "CTFError",
    "CTFRegistry",
    "Challenge",
    "ChallengeNotFoundError",
    "Submission",
    "global_registry",
]
