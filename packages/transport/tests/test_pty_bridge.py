"""Tests for the PTY bridge module.

These don't spawn an actual shell — that would tie test runtime to
the host's $SHELL behaviour. Instead we verify the small pure-Python
surfaces and the env-gate.
"""

from __future__ import annotations

import os

import pytest
from penumbra_transport.pty_bridge import _resolve_shell, pty_enabled


def test_pty_enabled_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PENUMBRA_ENABLE_PTY", raising=False)
    assert pty_enabled() is False


def test_pty_enabled_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PENUMBRA_ENABLE_PTY", "1")
    assert pty_enabled() is True


def test_resolve_shell_returns_existing_executable() -> None:
    shell = _resolve_shell()
    assert os.path.isfile(shell)
    assert os.access(shell, os.X_OK)


def test_resolve_shell_falls_back_when_shell_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHELL", raising=False)
    shell = _resolve_shell()
    assert shell == "/bin/zsh"
