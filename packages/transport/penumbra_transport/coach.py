"""Dashboard-side command runner for the attacker + shell-coach CLIs.

Concept taught: defence-in-depth for a "run a shell command from the
browser" feature. The naïve version is a remote-code-execution gift
to the network; the safe version (this one) constrains the input to a
small, well-known set of commands and runs them with a hard timeout.

Rules
- Only commands whose first token matches an allow-list prefix
  (``pna``, ``psh``) may run.
- Arguments are tokenised via ``shlex`` — never passed to a shell
  with ``shell=True``.
- Each run has a 30-second wall-clock cap.
- The dashboard panel exposes a *list* of commands the user can
  click; free-form input still goes through the same allow-list.
"""

from __future__ import annotations

import asyncio
import shlex
import shutil
from dataclasses import dataclass
from typing import Final

ALLOWED_BINARIES: Final[frozenset[str]] = frozenset({"pna", "psh"})
TIMEOUT_SECONDS: Final[float] = 30.0


@dataclass(frozen=True, slots=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool


class DisallowedCommandError(ValueError):
    """Raised when a request asks for a binary outside the allow-list."""


async def run_command(command_line: str) -> CommandResult:
    """Tokenise + validate + run + capture output."""
    argv = shlex.split(command_line)
    if not argv:
        raise DisallowedCommandError("empty command")
    binary = argv[0]
    if binary not in ALLOWED_BINARIES:
        raise DisallowedCommandError(
            f"binary '{binary}' is not in the allow-list {sorted(ALLOWED_BINARIES)}"
        )
    resolved = shutil.which(binary)
    if resolved is None:
        return CommandResult(
            exit_code=127,
            stdout="",
            stderr=f"{binary} not on PATH — install with `uv tool install ./packages/{binary}`",
            timed_out=False,
        )
    process = await asyncio.create_subprocess_exec(
        resolved,
        *argv[1:],
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=TIMEOUT_SECONDS
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        return CommandResult(
            exit_code=124,
            stdout="",
            stderr=f"command timed out after {TIMEOUT_SECONDS:.0f}s",
            timed_out=True,
        )
    return CommandResult(
        exit_code=int(process.returncode or 0),
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
        timed_out=False,
    )
