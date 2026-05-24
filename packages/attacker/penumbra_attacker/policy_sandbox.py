"""Sandboxed Python policy injection for the live arena.

Concept taught: running untrusted user code SAFELY in a long-lived
server process means three orthogonal locks — a parser-level lock on
which AST nodes are even ALLOWED (no `import`, no `exec`, no `open`),
a namespace lock on what builtins the code can see, and a wall-clock
lock on how long any single call can spend. None of these three alone
is sufficient; together they give a pedagogical sandbox tight enough
to ship in a demo and loose enough that users can still write useful
attack policies on top of `numpy`.

What's intentionally NOT defended here: a determined attacker with
control of the sandboxed source can still consume memory, mutate
shared `numpy` arrays the host passes in, or hot-CPU the time budget.
That's fine for the educational target — the lab is single-tenant.
"""

from __future__ import annotations

import ast
import math
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np


class PolicySandboxError(Exception):
    """Base class for any sandbox rejection."""


class PolicyParseError(PolicySandboxError):
    """Source could not be parsed or used a forbidden AST node."""


class PolicyTimeoutError(PolicySandboxError):
    """Sandboxed call exceeded its wall-clock budget."""


class PolicyRuntimeError(PolicySandboxError):
    """Sandboxed call raised an exception."""


_FORBIDDEN_NAMES = frozenset(
    {
        "__import__",
        "open",
        "eval",
        "exec",
        "compile",
        "globals",
        "locals",
        "vars",
        "input",
        "exit",
        "quit",
        "breakpoint",
        "help",
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
        "memoryview",
        "object",
    }
)
_FORBIDDEN_AST = (
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.With,
    ast.AsyncWith,
    ast.AsyncFunctionDef,
    ast.AsyncFor,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
)
_ALLOWED_BUILTINS: Mapping[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "pow": pow,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
}


@dataclass(frozen=True, slots=True)
class RegisteredPolicy:
    """One sandboxed policy ready to evaluate."""

    name: str
    scope: str
    source: str
    fn: Callable[..., Any]


def _validate_source(source: str) -> ast.Module:
    """Parse + AST-walk the source; raise PolicyParseError on any forbidden node."""
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise PolicyParseError(f"syntax error: {exc.msg} at line {exc.lineno}") from exc
    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_AST):
            raise PolicyParseError(f"forbidden construct: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise PolicyParseError(f"forbidden name: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise PolicyParseError(f"forbidden dunder access: .{node.attr}")
    return tree


def _build_namespace() -> dict[str, Any]:
    """Whitelisted builtins + numpy + math, no `__import__`."""
    return {
        "__builtins__": dict(_ALLOWED_BUILTINS),
        "np": np,
        "numpy": np,
        "math": math,
    }


def _run_with_timeout(fn: Callable[..., Any], args: tuple[Any, ...], timeout_s: float) -> Any:
    """Call fn(*args) on a worker thread; raise PolicyTimeoutError if it
    hasn't returned within timeout_s. We can't kill the thread — the
    interpreter doesn't expose that — so a runaway call leaves the
    thread leaking until it exits. The dashboard documents this; the
    target use is a 50 ms policy step where a leak is irrelevant.
    """
    result: dict[str, Any] = {}

    def _target() -> None:
        try:
            result["value"] = fn(*args)
        except Exception as exc:
            result["error"] = exc

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        raise PolicyTimeoutError(f"policy exceeded {timeout_s * 1000:.0f} ms budget")
    if "error" in result:
        raise PolicyRuntimeError(str(result["error"])) from result["error"]
    return result.get("value")


class PolicySandbox:
    """Registry of sandboxed policies, keyed by name."""

    def __init__(self, *, call_timeout_s: float = 0.05) -> None:
        self._timeout = call_timeout_s
        self._policies: dict[str, RegisteredPolicy] = {}

    def register(self, name: str, code: str, scope: str = "all") -> RegisteredPolicy:
        """Compile `code` in a sandboxed namespace; require a top-level
        `policy(state, observation) -> action` callable.
        """
        if not name or not name.replace("_", "").replace("-", "").isalnum():
            raise PolicyParseError("name must be alphanumeric with _ or -")
        tree = _validate_source(code)
        namespace = _build_namespace()
        try:
            exec(compile(tree, filename=f"<policy:{name}>", mode="exec"), namespace)  # noqa: S102
        except Exception as exc:
            raise PolicyParseError(f"compile failed: {exc}") from exc
        fn = namespace.get("policy")
        if not callable(fn):
            raise PolicyParseError("source must define a callable `policy`")
        registered = RegisteredPolicy(name=name, scope=scope, source=code, fn=fn)
        self._policies[name] = registered
        return registered

    def unregister(self, name: str) -> bool:
        """Drop the named policy; return True iff it was present."""
        return self._policies.pop(name, None) is not None

    def list_registered(self) -> list[dict[str, str]]:
        """Public-safe summary for the /attacker/policies endpoint."""
        return [
            {"name": p.name, "scope": p.scope, "source_chars": str(len(p.source))}
            for p in self._policies.values()
        ]

    def get(self, name: str) -> RegisteredPolicy | None:
        return self._policies.get(name)

    def call(self, name: str, *args: Any) -> Any:
        """Run the named policy with `args` inside the time budget."""
        registered = self._policies.get(name)
        if registered is None:
            raise PolicyRuntimeError(f"no policy named {name!r}")
        return _run_with_timeout(registered.fn, args, self._timeout)


_GLOBAL = PolicySandbox()


def register_policy(name: str, code: str, scope: str = "all") -> RegisteredPolicy:
    """Module-level convenience for the FastAPI endpoint."""
    return _GLOBAL.register(name, code, scope)


def list_registered() -> list[dict[str, str]]:
    """Module-level convenience for the FastAPI endpoint."""
    return _GLOBAL.list_registered()


def unregister(name: str) -> bool:
    """Module-level convenience for the FastAPI endpoint."""
    return _GLOBAL.unregister(name)


def try_policy(name: str, *args: Any) -> Any:
    """Module-level convenience: invoke the registered policy once."""
    return _GLOBAL.call(name, *args)


def global_sandbox() -> PolicySandbox:
    """Expose the singleton for tests + advanced callers."""
    return _GLOBAL
