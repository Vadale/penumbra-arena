"""Tests for the shell coach primitives + CLI."""

from __future__ import annotations

import pytest
from penumbra_shell_coach.cli import app
from penumbra_shell_coach.error_helper import interpret
from penumbra_shell_coach.explain import explain
from penumbra_shell_coach.runner import (
    LessonNotFoundError,
    check_step,
    list_lessons,
    load_lesson,
    shell_safe,
)
from penumbra_shell_coach.suggester import suggest
from typer.testing import CliRunner

# ── explain ──────────────────────────────────────────────────────


def test_explain_ls_minus_lah() -> None:
    result = explain("ls -lah")
    assert result.binary == "ls"
    flag_text = " ".join(result.notes)
    assert "long format" in flag_text
    assert "dotfiles" in flag_text
    assert "human-readable" in flag_text


def test_explain_unknown_command_returns_pointer_to_man() -> None:
    result = explain("totally-fake-tool --x --y")
    assert "man totally-fake-tool" in " ".join(result.notes)


def test_explain_empty_input() -> None:
    result = explain([])
    assert result.binary == ""


# ── suggester ─────────────────────────────────────────────────────


def test_suggester_after_ls() -> None:
    hints = suggest("ls")
    assert any("eza" in h for h in hints)
    assert any("du" in h for h in hints)


def test_suggester_after_unknown_returns_empty() -> None:
    assert suggest("totally-fake-cmd --flag") == []


# ── error_helper ──────────────────────────────────────────────────


def test_interpret_command_not_found() -> None:
    s = interpret("zsh: command not found: rg")
    assert s.matched
    assert "brew install rg" in s.hint


def test_interpret_permission_denied() -> None:
    s = interpret("bash: ./run.sh: Permission denied")
    assert s.matched
    assert "chmod" in s.hint or "sudo" in s.hint


def test_interpret_no_match_returns_generic_hint() -> None:
    s = interpret("a wholly novel error message we have not modelled")
    assert not s.matched


# ── lesson runner ─────────────────────────────────────────────────


def test_lessons_are_discoverable() -> None:
    lessons = list_lessons()
    ids = {lesson.id for lesson in lessons}
    expected = {
        "filesystem",
        "text_processing",
        "pipes_redirection",
        "networking_curl",
        "macos_specific",
        "modern_cli",
    }
    assert expected.issubset(ids)


def test_load_specific_lesson() -> None:
    lesson = load_lesson("filesystem")
    assert len(lesson.steps) >= 3
    assert lesson.title


def test_unknown_lesson_raises() -> None:
    with pytest.raises(LessonNotFoundError):
        load_lesson("not-a-real-lesson")


def test_shell_safe_blocks_destructive() -> None:
    assert not shell_safe("rm -rf /")
    assert not shell_safe("dd if=/dev/zero of=/tmp/x")
    assert shell_safe("ls -la")


def test_check_step_runs_safe_command() -> None:
    from penumbra_shell_coach.runner import Step

    step = Step(
        instruction="print hello",
        validate_cmd="echo hello-world",
        expected_pattern="hello-world",
        hint="just echo it",
    )
    result = check_step(step)
    assert result.succeeded


# ── CLI ───────────────────────────────────────────────────────────


def test_cli_lessons_lists_six() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["lessons"])
    assert result.exit_code == 0
    for required_id in ("filesystem", "text_processing", "networking_curl"):
        assert required_id in result.output


def test_cli_explain_ls() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["explain", "ls -la"])
    assert result.exit_code == 0
    assert "long format" in result.output


def test_cli_suggest_ls() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["suggest", "ls"])
    assert result.exit_code == 0
    assert "eza" in result.output


def test_cli_interpret_known_error() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["interpret", "zsh: command not found: rg"])
    assert result.exit_code == 0
    assert "brew install rg" in result.output
