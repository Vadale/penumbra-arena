"""Jupyter / IPython bridge for the Penumbra arena.

Concept taught: IPython magics make a server-side process feel local
in a notebook. We expose three magics — `%penumbra connect` to attach
to a running FastAPI orchestrator, `%penumbra snapshot` to capture
the latest `/state` payload as a cell value, and `%%penumbra attack`
to evaluate a Python cell body inside the SAME sandbox the
`/attacker/policy` endpoint uses. The bridge is intentionally
read-only over HTTP: no writes flow from the notebook into the
running arena, only out from it.
"""

from __future__ import annotations

import shlex
from typing import Any

import httpx
from penumbra_attacker.policy_sandbox import (
    PolicyParseError,
    PolicyRuntimeError,
    PolicyTimeoutError,
    global_sandbox,
)


class PenumbraNotebookError(Exception):
    """Base class for notebook-bridge errors."""


class _PenumbraSession:
    """Module-level state for the active connection."""

    def __init__(self) -> None:
        self.base_url: str | None = None

    def connect(self, url: str) -> dict[str, Any]:
        self.base_url = url.rstrip("/")
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=2.0)
        except httpx.HTTPError as exc:
            raise PenumbraNotebookError(f"could not reach {self.base_url}: {exc}") from exc
        if r.status_code != 200:
            raise PenumbraNotebookError(f"unexpected status {r.status_code} from /health")
        return {"connected": True, "base_url": self.base_url, "health": r.json()}

    def snapshot(self) -> dict[str, Any]:
        if self.base_url is None:
            raise PenumbraNotebookError("not connected — call %penumbra connect first")
        r = httpx.get(f"{self.base_url}/state", timeout=4.0)
        if r.status_code != 200:
            raise PenumbraNotebookError(f"unexpected status {r.status_code} from /state")
        return r.json()


_SESSION = _PenumbraSession()


def line_magic(line: str) -> Any:
    """Implementation of `%penumbra <command> [args]`.

    Public so it is reachable from tests without requiring an IPython
    kernel to be running.
    """
    tokens = shlex.split(line.strip())
    if not tokens:
        return {"usage": "%penumbra connect <url> | %penumbra snapshot"}
    cmd = tokens[0]
    if cmd == "connect":
        url = tokens[1] if len(tokens) > 1 else "http://localhost:8000"
        return _SESSION.connect(url)
    if cmd == "snapshot":
        return _SESSION.snapshot()
    raise PenumbraNotebookError(f"unknown subcommand {cmd!r}")


def cell_magic(line: str, cell: str) -> dict[str, Any]:
    """Implementation of `%%penumbra attack` — eval `cell` in the sandbox.

    The cell must define a top-level `policy(state, observation)`
    callable; we register it under a name derived from the line
    argument (default "notebook_attack") and call it once with two
    empty dicts so the user sees an immediate result. Re-registering
    overwrites the previous version.
    """
    tokens = shlex.split(line.strip()) if line.strip() else ["attack", "notebook_attack"]
    if tokens[0] != "attack":
        raise PenumbraNotebookError("only `%%penumbra attack` is supported")
    name = tokens[1] if len(tokens) > 1 else "notebook_attack"
    sandbox = global_sandbox()
    try:
        registered = sandbox.register(name, cell, scope="notebook")
        result = sandbox.call(name, {}, {})
    except PolicyParseError as exc:
        return {"name": name, "ok": False, "error": f"parse: {exc}"}
    except PolicyTimeoutError as exc:
        return {"name": name, "ok": False, "error": f"timeout: {exc}"}
    except PolicyRuntimeError as exc:
        return {"name": name, "ok": False, "error": f"runtime: {exc}"}
    return {
        "name": registered.name,
        "ok": True,
        "result": result,
        "source_chars": len(registered.source),
    }


def load_ipython_extension(ipython: Any) -> None:
    """Hook called by IPython on `%load_ext penumbra_notebook`."""
    ipython.register_magic_function(line_magic, magic_kind="line", magic_name="penumbra")
    ipython.register_magic_function(cell_magic, magic_kind="cell", magic_name="penumbra")


__all__ = [
    "PenumbraNotebookError",
    "cell_magic",
    "line_magic",
    "load_ipython_extension",
]
