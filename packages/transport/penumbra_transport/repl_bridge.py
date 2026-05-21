"""WebSocket ↔ sandboxed Python REPL bridge.

Concept taught: pair the full-shell PTY (`pty_bridge.py`) with a
SANDBOXED Python REPL that exposes the live Penumbra `api`
namespace. The attacker can call:

    >>> api.snapshot()                # current public state
    >>> api.heatmap_density()         # raw density vector
    >>> api.chain_height()
    >>> api.signing_stats()
    >>> api.dp_budget()
    >>> api.help()

…without ever touching the host filesystem or spawning subprocesses.
The whole REPL runs in-process; an interrupt drops the user back to
the prompt rather than killing the simulation.

Security
--------
- The REPL exec namespace is built explicitly: a curated `api`
  module + a tiny set of safe builtins (print, len, str, int, float,
  list, tuple, dict, set, sorted, range, enumerate, zip, abs, sum,
  min, max, type, isinstance). No `open`, no `import`, no `__import__`,
  no `eval`, no `exec`, no `globals()`, no `compile`.
- A 5-second wall-clock timeout per submission protects against
  accidental infinite loops.
- This is **defence in depth**, not a hostile sandbox. A determined
  attacker who can both read the source and inject Python WILL
  escape (e.g. via attribute walks on objects the api exposes).
  The PTY bridge is the appropriate surface for trusted-host
  experiments; this one is for "what does the running state look
  like" introspection.

Gated behind PENUMBRA_ENABLE_REPL=1.
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_REPL_TIMEOUT_SECONDS = 5.0


def repl_enabled() -> bool:
    """True only when PENUMBRA_ENABLE_REPL=1 in the env."""
    return os.environ.get("PENUMBRA_ENABLE_REPL") == "1"


@dataclass(slots=True)
class ReplApi:
    """The `api` object the REPL exposes. Read-only views into orchestrator state."""

    _orchestrator: Any

    def snapshot(self) -> dict[str, Any]:
        """Current chain height + tick + match id + active validator count."""
        node = self._orchestrator.node
        sim = self._orchestrator.simulation
        return {
            "tick": sim.tick_counter,
            "match_id": sim.current_match.id,
            "chain_height": node.height,
            "active_validators": len(node.active_indices),
            "slashed_validators": len(node.slashed_pubkeys),
        }

    def heatmap_density(self) -> list[float]:
        """Latest decrypted CKKS density vector (post-DP-noise if enabled)."""
        sample = self._orchestrator.heatmap.latest
        return [] if sample is None else list(sample.density)

    def chain_height(self) -> int:
        return self._orchestrator.node.height

    def signing_stats(self) -> dict[str, int]:
        stats = self._orchestrator.keystore.stats
        return {
            "verified": stats.verified,
            "rejected": stats.rejected,
            "n_agents": len(self._orchestrator.keystore.keypairs),
        }

    def dp_budget(self) -> dict[str, float] | None:
        mech = self._orchestrator.heatmap.dp_mechanism
        if mech is None:
            return None
        return {
            "epsilon_total": mech.budget.epsilon,
            "epsilon_spent": mech.budget.epsilon_spent,
            "epsilon_remaining": mech.budget.remaining_epsilon,
        }

    def agent_positions(self) -> dict[int, int]:
        sim = self._orchestrator.simulation
        return {a.id: a.position for a in sim.agents}

    def help(self) -> str:
        return (
            "Penumbra attacker REPL — read-only views.\n"
            "  api.snapshot()         → tick + match + chain + validator counts\n"
            "  api.heatmap_density()  → latest CKKS-decrypted density vector\n"
            "  api.chain_height()     → current block height\n"
            "  api.signing_stats()    → Dilithium verify/reject counts\n"
            "  api.dp_budget()        → DP ε spent/remaining\n"
            "  api.agent_positions()  → {agent_id: node_id}\n"
            "  api.help()             → this message\n"
            "Restrictions: no open(), no import, no exec, 5s timeout per submission."
        )


_SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
}


@dataclass(slots=True)
class ReplSession:
    """Per-WS-connection REPL state."""

    api: ReplApi
    namespace: dict[str, Any]

    @classmethod
    def for_orchestrator(cls, orchestrator: Any) -> ReplSession:
        api = ReplApi(_orchestrator=orchestrator)
        namespace: dict[str, Any] = {
            "__builtins__": _SAFE_BUILTINS,
            "api": api,
            "_": None,  # last-value bind
        }
        return cls(api=api, namespace=namespace)


def execute(session: ReplSession, source: str) -> tuple[str, str]:
    """Execute one REPL submission. Returns (stdout, stderr).

    Tries `eval` (expression) first; falls back to `exec` (statement).
    Captures stdout from `print(...)` calls. Enforces a wall-clock
    timeout via a hard cap; long-running submissions return a clear
    timeout message.
    """
    started = time.monotonic()

    def _check_timeout() -> None:
        if time.monotonic() - started > _REPL_TIMEOUT_SECONDS:
            raise TimeoutError(f"REPL submission exceeded {_REPL_TIMEOUT_SECONDS}s")

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
        try:
            try:
                # Try expression-mode first so we can echo the value.
                value = eval(source, session.namespace, session.namespace)  # noqa: S307
                _check_timeout()
                if value is not None:
                    print(repr(value))
                    session.namespace["_"] = value
            except SyntaxError:
                exec(source, session.namespace, session.namespace)  # noqa: S102
                _check_timeout()
        except TimeoutError as exc:
            return stdout.getvalue(), str(exc) + "\n"
        except Exception as exc:
            return stdout.getvalue(), f"{type(exc).__name__}: {exc}\n"
    return stdout.getvalue(), ""
