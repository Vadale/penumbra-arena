"""Command explainer.

Concept taught: how a static knowledge base of binary-and-flag
semantics powers a man-page-style explainer that is faster than
`man` and reads like an annotated diff — making the learner's
"why does this flag exist" question answerable in one screen.

Given an argv list, look up the binary's flags from a static knowledge
base and return a labelled breakdown the user can read at a glance.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

_COMMAND_DB: dict[str, dict[str, str]] = {
    "ls": {
        "-l": "long format: permissions + owner + size + mtime",
        "-a": "include dotfiles",
        "-h": "human-readable sizes (K/M/G)",
        "-S": "sort by size",
        "-t": "sort by mtime",
        "-r": "reverse sort order",
        "-R": "recurse into subdirectories",
    },
    "grep": {
        "-i": "case-insensitive match",
        "-n": "show line numbers",
        "-r": "recurse into directories",
        "-v": "invert match",
        "-E": "extended regex",
        "-c": "count matching lines",
        "-l": "print only file names",
    },
    "rg": {
        "-i": "case-insensitive match",
        "-S": "smart case (case-sensitive iff pattern has uppercase)",
        "-l": "print only file names",
        "-w": "match whole words",
        "-A": "show N lines AFTER each match",
        "-B": "show N lines BEFORE each match",
        "-C": "show N lines of context around each match",
        "--type": "filter by file type (e.g. py, ts, md)",
    },
    "find": {
        "-name": "match by name pattern (use quotes!)",
        "-type": "f=file, d=dir, l=link",
        "-mtime": "modified time in days (negative = within)",
        "-size": "+1M = larger than 1MB, -100k = smaller than 100KB",
        "-exec": "run a command on each match (terminate with \\;)",
        "-print0": "NUL-separate output for xargs -0",
    },
    "curl": {
        "-X": "HTTP method (GET/POST/PUT/DELETE/...)",
        "-H": "add a header",
        "-d": "POST body data",
        "-i": "show response headers",
        "-I": "HEAD request only (response headers, no body)",
        "-L": "follow redirects",
        "-s": "silent (no progress meter)",
        "-o": "write body to file",
        "-u": "user:password for basic auth",
    },
    "tar": {
        "-c": "create archive",
        "-x": "extract archive",
        "-f": "filename (must be followed by the archive name)",
        "-z": "gzip compression",
        "-j": "bzip2 compression",
        "-J": "xz compression",
        "-v": "verbose",
    },
    "chmod": {
        "u+x": "add execute for owner",
        "g+w": "add write for group",
        "o-r": "remove read for others",
        "+x": "add execute for all",
        "755": "rwxr-xr-x (typical script)",
        "644": "rw-r--r-- (typical file)",
        "600": "rw------- (private)",
    },
    "ps": {
        "aux": "BSD: all users, all procs, with details",
        "-ef": "SysV: all procs with full command line",
    },
    "kill": {
        "-9": "SIGKILL (force, no cleanup)",
        "-15": "SIGTERM (graceful)",
        "-HUP": "SIGHUP (often reload config)",
    },
    "git": {
        "status": "working-tree state",
        "log": "history (--oneline for compact)",
        "diff": "unstaged changes (--cached for staged)",
        "add": "stage changes (-p for hunk-by-hunk)",
        "commit": "create commit (-m for message)",
        "push": "send to remote",
        "pull": "fetch + merge",
        "checkout": "switch branch / restore files",
        "switch": "switch branch (safer than checkout)",
        "restore": "restore files from index/HEAD",
    },
    "brew": {
        "install": "add a formula or cask",
        "uninstall": "remove a formula",
        "update": "refresh the formula index",
        "upgrade": "upgrade installed formulae",
        "list": "list installed formulae",
        "info": "show formula details",
        "search": "search formulae by name",
        "cleanup": "remove old versions",
    },
}


@dataclass(frozen=True, slots=True)
class Explanation:
    binary: str
    notes: tuple[str, ...]


def explain(command: str | list[str]) -> Explanation:
    """Parse `command` and return labelled flag descriptions."""
    argv = shlex.split(command) if isinstance(command, str) else list(command)
    if not argv:
        return Explanation(binary="", notes=("(empty command)",))
    binary = argv[0]
    db = _COMMAND_DB.get(binary)
    if db is None:
        return Explanation(
            binary=binary,
            notes=(f"no curated entry for `{binary}` — run `man {binary}` for the full reference",),
        )
    notes: list[str] = []
    for token in argv[1:]:
        if token in db:
            notes.append(f"{token} — {db[token]}")
        elif token.startswith("-") and len(token) > 2 and not token.startswith("--"):
            # Combined short flags: -lah → -l -a -h
            for ch in token[1:]:
                short = f"-{ch}"
                if short in db:
                    notes.append(f"{short} (from `{token}`) — {db[short]}")
    if not notes:
        notes.append(f"`{binary}` recognised; no documented flags present in the command")
    return Explanation(binary=binary, notes=tuple(notes))
