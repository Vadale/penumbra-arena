"""Tests for the sandboxed-policy registry."""

from __future__ import annotations

import pytest
from penumbra_attacker.policy_sandbox import (
    PolicyParseError,
    PolicyRuntimeError,
    PolicySandbox,
    PolicyTimeoutError,
)


def test_register_and_call_simple_policy() -> None:
    sb = PolicySandbox()
    sb.register("noop", "def policy(state, obs):\n    return 0\n")
    assert sb.call("noop", {}, {}) == 0
    assert any(p["name"] == "noop" for p in sb.list_registered())


def test_register_uses_numpy_and_math() -> None:
    sb = PolicySandbox()
    src = "def policy(state, obs):\n    return int(np.argmax(np.array([1, 2, 3]))) + math.floor(0.9)\n"
    sb.register("argmax", src)
    assert sb.call("argmax", {}, {}) == 2


@pytest.mark.parametrize(
    "snippet",
    [
        "import os\ndef policy(s, o):\n    return 0\n",
        "def policy(s, o):\n    return open('/etc/passwd').read()\n",
        "def policy(s, o):\n    return eval('1+1')\n",
        "def policy(s, o):\n    return __import__('os').getuid()\n",
        "def policy(s, o):\n    return s.__class__.__bases__\n",
    ],
)
def test_register_rejects_forbidden_sources(snippet: str) -> None:
    sb = PolicySandbox()
    with pytest.raises(PolicyParseError):
        sb.register("bad", snippet)


def test_unregister_returns_true_then_false() -> None:
    sb = PolicySandbox()
    sb.register("p", "def policy(s, o):\n    return 0\n")
    assert sb.unregister("p") is True
    assert sb.unregister("p") is False


def test_runtime_error_is_wrapped() -> None:
    sb = PolicySandbox()
    sb.register("crash", "def policy(s, o):\n    return 1 / 0\n")
    with pytest.raises(PolicyRuntimeError):
        sb.call("crash", {}, {})


def test_call_unknown_policy_raises() -> None:
    sb = PolicySandbox()
    with pytest.raises(PolicyRuntimeError):
        sb.call("missing")


def test_timeout_enforced() -> None:
    sb = PolicySandbox(call_timeout_s=0.05)
    sb.register(
        "loop",
        "def policy(s, o):\n    x = 0\n    while True:\n        x = (x + 1) % 1000\n    return x\n",
    )
    with pytest.raises(PolicyTimeoutError):
        sb.call("loop", {}, {})


def test_invalid_name_rejected() -> None:
    sb = PolicySandbox()
    with pytest.raises(PolicyParseError):
        sb.register("bad name!", "def policy(s, o):\n    return 0\n")


def test_missing_policy_callable_rejected() -> None:
    sb = PolicySandbox()
    with pytest.raises(PolicyParseError):
        sb.register("noop", "x = 1\n")
