"""Error helper: interpret common stderr messages and propose a fix.

The pattern → fix mapping is hand-curated. We match the *first* regex
that hits; the user can always read the full error too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"command not found: (\S+)"),
        "`{0}` is not installed (or not in PATH). On Mac: `brew install {0}` (or check `which {0}`).",
    ),
    (
        re.compile(r"Permission denied", re.IGNORECASE),
        "Permission denied. Inspect with `ls -la` and consider `chmod +x <file>` (for execute) or `sudo` if the resource genuinely needs root.",
    ),
    (
        re.compile(r"No such file or directory"),
        "The path does not exist. Verify with `ls <dir>` or use tab-completion. On macOS, `mdfind -name <name>` can help find a misplaced file.",
    ),
    (
        re.compile(r"port .*already in use|Address already in use"),
        "Port is busy. Find the holder with `lsof -i :<port>` and either kill it (`kill -9 <pid>`) or use a different port.",
    ),
    (
        re.compile(r"ImportError|ModuleNotFoundError: No module named '(\S+)'"),
        "Python can't import `{0}` — usually means it's missing from the active environment. `uv add {0}` or activate the right venv.",
    ),
    (
        re.compile(r"fatal: not a git repository"),
        "You are not inside a git repo. `git init` if you want to create one here, or `cd` into a tracked directory.",
    ),
    (
        re.compile(r"could not connect to server|Connection refused"),
        "The service you tried to reach is not accepting connections. Verify it's running (`ps`, `lsof -i`, `curl localhost:<port>/health`).",
    ),
    (
        re.compile(r"SSL.*certificate verify failed", re.IGNORECASE),
        "TLS certificate problem. On macOS this often means missing CA bundle — `/Applications/Python\\ 3.x/Install\\ Certificates.command` once, or set REQUESTS_CA_BUNDLE.",
    ),
    (
        re.compile(r"docker: Cannot connect to the Docker daemon"),
        "Docker Desktop isn't running. Start it from /Applications, then re-run.",
    ),
    (
        re.compile(r"zsh: bad pattern"),
        "Zsh tried to glob a pattern that didn't match. Quote it: `'<pattern>'` or use `setopt nullglob` if that's intentional.",
    ),
]


@dataclass(frozen=True, slots=True)
class Suggestion:
    matched: bool
    hint: str


def interpret(stderr: str) -> Suggestion:
    """Return a one-line fix hint for the first matching pattern in `stderr`."""
    for pattern, template in _PATTERNS:
        match = pattern.search(stderr)
        if match is not None:
            return Suggestion(matched=True, hint=template.format(*match.groups()))
    return Suggestion(
        matched=False,
        hint="No curated hint matches this error — read it carefully and try `man <command>`.",
    )
