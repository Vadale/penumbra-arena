"""Tests for the dashboard command runner."""

from __future__ import annotations

import pytest
from penumbra_transport.coach import (
    ALLOWED_BINARIES,
    DisallowedCommandError,
    run_command,
)


@pytest.mark.asyncio
async def test_rejects_unknown_binary() -> None:
    with pytest.raises(DisallowedCommandError):
        await run_command("ls -la")


@pytest.mark.asyncio
async def test_rejects_empty() -> None:
    with pytest.raises(DisallowedCommandError):
        await run_command("")


@pytest.mark.asyncio
async def test_psh_lessons_runs_if_installed() -> None:
    """`psh` is installed as a uv tool; running its 'lessons' subcommand
    should exit cleanly."""
    result = await run_command("psh lessons")
    # 127 = binary not on PATH (acceptable in fresh CI); 0 = success.
    assert result.exit_code in {0, 127}
    if result.exit_code == 0:
        # The lessons table mentions at least one curated track.
        assert "filesystem" in result.stdout or "lessons" in result.stdout


def test_allow_list_is_small() -> None:
    """We deliberately keep the allow-list tiny."""
    assert {"pna", "psh"} == ALLOWED_BINARIES
