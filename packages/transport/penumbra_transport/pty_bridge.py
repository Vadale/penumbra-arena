"""WebSocket ↔ macOS zsh PTY bridge.

Concept taught: a pseudo-terminal (PTY) is the kernel-level
abstraction that makes a terminal-emulator-talking-to-a-shell work.
The "master" side reads what the program wrote and writes what the
user typed; the "slave" side is the program's stdin/stdout/stderr.
zsh thinks it's talking to a real terminal because the slave fd has
isatty()==True.

This module spawns zsh on the slave side and pumps both directions
between the master fd and a WebSocket. xterm.js on the browser side
serialises keystrokes + window resizes; the PTY echoes characters,
colours, control sequences, and prompts come back over the WS.

Security
--------
The bridge runs whatever shell the user has on their PATH. There is
NO allow-list, NO timeout, NO command parsing — that's the point.
For a restricted "only run pna/psh" UX we already have the Coach
panel. This bridge is the *full Mac terminal* in the dashboard.

Gated behind `PENUMBRA_ENABLE_PTY=1` so a production deployment
doesn't accidentally expose remote-code-execution over a localhost
WS. The /ws/pty endpoint returns 403 when the flag isn't set.

References
----------
- `man pty(4)` on macOS for the BSD PTY semantics we ride on top of.
- Asyncio loop integration via `loop.add_reader` — the canonical
  pattern for non-blocking fd reads in an asyncio app.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import logging
import os
import pty
import shutil
import signal
import struct
import termios
from collections.abc import AsyncIterator
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def pty_enabled() -> bool:
    """True only when PENUMBRA_ENABLE_PTY=1 in the env."""
    return os.environ.get("PENUMBRA_ENABLE_PTY") == "1"


def _resolve_shell() -> str:
    """Return the path of the shell to spawn.

    Honours $SHELL if set and executable; falls back to /bin/zsh on macOS.
    """
    shell = os.environ.get("SHELL")
    if shell and shutil.which(shell):
        return shell
    return "/bin/zsh"


@dataclass(slots=True)
class PtySession:
    """One spawned shell + its master fd. Lives for one WS connection."""

    pid: int
    master_fd: int

    async def write(self, data: bytes) -> None:
        """Send keystrokes to the shell."""
        await asyncio.to_thread(os.write, self.master_fd, data)

    def resize(self, rows: int, cols: int) -> None:
        """Tell the kernel the new window size so curses-apps re-flow."""
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        try:
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        except OSError as exc:
            logger.debug("PTY resize failed (process likely exited): %s", exc)

    def close(self) -> None:
        """SIGTERM the shell + close the master fd."""
        with contextlib.suppress(ProcessLookupError):
            os.kill(self.pid, signal.SIGTERM)
        with contextlib.suppress(OSError):
            os.close(self.master_fd)


def spawn_shell() -> PtySession:
    """Fork off a zsh under a fresh PTY pair. Returns the master-side handle."""
    pid, master_fd = pty.fork()
    if pid == 0:
        # Child: exec the shell, replacing the Python interpreter.
        os.execvp(_resolve_shell(), [_resolve_shell()])  # noqa: S606 — intentional shell spawn
        # execvp doesn't return on success.
        return None  # type: ignore[unreachable]
    return PtySession(pid=pid, master_fd=master_fd)


async def read_pty(session: PtySession) -> AsyncIterator[bytes]:
    """Async generator yielding bytes the shell writes to its stdout/stderr.

    Uses a thread for the blocking `os.read`; an `add_reader` approach
    would also work but the thread pattern is simpler and the data
    rate of a terminal session is trivially bandwidth-bound.
    """
    while True:
        try:
            chunk = await asyncio.to_thread(os.read, session.master_fd, 4096)
        except OSError:
            return
        if not chunk:
            return
        yield chunk
