"""Tests for the CTF harness."""

from __future__ import annotations

import pytest
from penumbra_ctf import (
    CHALLENGES_DIR,
    ChallengeNotFoundError,
    CTFRegistry,
)


def _fresh() -> CTFRegistry:
    reg = CTFRegistry()
    reg.load_dir(CHALLENGES_DIR)
    return reg


def test_loads_five_starter_challenges() -> None:
    reg = _fresh()
    ids = {c["id"] for c in reg.list_summaries()}
    assert ids == {
        "ctf-dp-recon-001",
        "ctf-linkability-002",
        "ctf-replay-003",
        "ctf-byzantine-004",
        "ctf-snark-forge-005",
    }


def test_summaries_expose_setup_and_acceptance() -> None:
    reg = _fresh()
    target = next(c for c in reg.list_summaries() if c["id"] == "ctf-dp-recon-001")
    assert target["title"].startswith("Reconstruct")
    assert target["setup"]["dp_epsilon"] == pytest.approx(0.1)
    assert target["acceptance"]["predict_position_within"] == 2


def test_submit_wrong_flag_recorded_but_not_correct() -> None:
    reg = _fresh()
    result = reg.submit("ctf-replay-003", "PEN{nope}", session_id="alice")
    assert result["correct"] is False
    assert reg.leaderboard("ctf-replay-003") == []


def test_submit_correct_flag_shows_on_leaderboard() -> None:
    reg = _fresh()
    expected = reg.challenges["ctf-dp-recon-001"].expected_flag()
    reg.submit("ctf-dp-recon-001", expected, session_id="alice")
    reg.submit("ctf-dp-recon-001", expected, session_id="bob")
    board = reg.leaderboard("ctf-dp-recon-001")
    assert [row["session_id"] for row in board] == ["alice", "bob"]
    assert [row["rank"] for row in board] == [1, 2]


def test_unknown_challenge_raises() -> None:
    reg = _fresh()
    with pytest.raises(ChallengeNotFoundError):
        reg.submit("ctf-does-not-exist", "x", session_id="alice")
    with pytest.raises(ChallengeNotFoundError):
        reg.leaderboard("ctf-does-not-exist")


def test_flag_template_resolves_salt_hash() -> None:
    reg = _fresh()
    flag = reg.challenges["ctf-snark-forge-005"].expected_flag()
    assert flag.startswith("PEN{forge_")
    assert "{{" not in flag
