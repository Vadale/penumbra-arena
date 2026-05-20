"""Rule-based "next command" suggester.

No LLM call required — these are deterministic heuristics keyed on the
*shape* of the user's last command. The point is to bridge from a
classic Unix command to its modern replacement, or to compose simple
commands into more powerful pipelines.
"""

from __future__ import annotations

import shlex

_RULES: list[tuple[str, list[str]]] = [
    (
        "ls",
        [
            "ls -lah                      # long + dotfiles + human sizes",
            "eza --tree -L 2              # modern tree-style listing",
            "du -sh *                     # size of each entry",
        ],
    ),
    (
        "cat",
        [
            "bat <file>                   # syntax-highlighted cat",
            "less <file>                  # paged view (q to quit)",
        ],
    ),
    (
        "grep",
        [
            "rg <pattern> <path>          # ripgrep: faster + .gitignore aware",
            "grep -rn <pattern> .         # recursive with line numbers",
        ],
    ),
    (
        "find",
        [
            "fd <name> .                  # faster + cleaner find replacement",
            "find . -name '*.py' -mtime -7  # python files modified in 7 days",
        ],
    ),
    (
        "cd",
        [
            "zoxide add <dir>             # learn this dir for `z` fuzzy jumps",
            "pwd                          # print the new working directory",
        ],
    ),
    (
        "ps",
        [
            "ps aux | grep <name>         # filter by process name",
            "lsof -i :<port>              # who is listening on a port",
            "top -o cpu                   # interactive process viewer",
        ],
    ),
    (
        "curl",
        [
            "curl -I <url>                # HEAD request — show response headers",
            "curl -L <url> | jq '.'       # follow redirects + pretty-print JSON",
            "httpie GET <url>             # HTTPie: nicer ergonomics",
        ],
    ),
]


def suggest(last_command: str) -> list[str]:
    """Return suggested next commands based on the binary in `last_command`."""
    argv = shlex.split(last_command)
    if not argv:
        return []
    binary = argv[0]
    for prefix, hints in _RULES:
        if binary == prefix:
            return list(hints)
    return []
