"""Tests for the sandboxed Python REPL bridge."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from penumbra_transport.repl_bridge import ReplSession, execute, repl_enabled


@dataclass
class _FakeAgent:
    id: int
    position: int


@dataclass
class _FakeMatch:
    id: int = 7


@dataclass
class _FakeSim:
    tick_counter: int = 99
    current_match: _FakeMatch | None = None
    agents: tuple[_FakeAgent, ...] = ()


@dataclass
class _FakeKeyStats:
    verified: int = 5
    rejected: int = 0


@dataclass
class _FakeKeystore:
    stats: _FakeKeyStats
    keypairs: tuple[object, ...] = ()


@dataclass
class _FakeNode:
    height: int = 3
    active_indices: set[int] = None  # type: ignore[assignment]
    slashed_pubkeys: set[bytes] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.active_indices is None:
            self.active_indices = {0, 1, 2}
        if self.slashed_pubkeys is None:
            self.slashed_pubkeys = set()


@dataclass
class _FakeOrchestrator:
    simulation: _FakeSim
    node: _FakeNode
    keystore: _FakeKeystore

    class _FakeHeatmap:
        latest = None
        dp_mechanism = None

    heatmap = _FakeHeatmap()


def _build_session() -> ReplSession:
    orchestrator = _FakeOrchestrator(
        simulation=_FakeSim(
            current_match=_FakeMatch(),
            agents=(_FakeAgent(0, 12), _FakeAgent(1, 7)),
        ),
        node=_FakeNode(),
        keystore=_FakeKeystore(stats=_FakeKeyStats()),
    )
    return ReplSession.for_orchestrator(orchestrator)


def test_repl_enabled_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PENUMBRA_ENABLE_REPL", raising=False)
    assert repl_enabled() is False


def test_repl_enabled_on_with_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PENUMBRA_ENABLE_REPL", "1")
    assert repl_enabled() is True


def test_execute_evaluates_expression() -> None:
    session = _build_session()
    stdout, stderr = execute(session, "2 + 3")
    assert stderr == ""
    assert "5" in stdout


def test_execute_runs_api_method() -> None:
    session = _build_session()
    stdout, stderr = execute(session, "api.chain_height()")
    assert stderr == ""
    assert "3" in stdout


def test_execute_runs_statement() -> None:
    session = _build_session()
    stdout, stderr = execute(session, "x = api.chain_height() * 2\nprint(x)")
    assert stderr == ""
    assert "6" in stdout


def test_execute_forbids_import() -> None:
    session = _build_session()
    _, stderr = execute(session, "import os")
    assert "NameError" in stderr or "Error" in stderr


def test_execute_forbids_open() -> None:
    session = _build_session()
    _, stderr = execute(session, "open('/etc/passwd')")
    assert "NameError" in stderr


def test_execute_captures_last_value_in_underscore() -> None:
    session = _build_session()
    execute(session, "42")
    stdout, stderr = execute(session, "_ + 1")
    assert stderr == ""
    assert "43" in stdout


def test_api_help_returns_banner() -> None:
    session = _build_session()
    stdout, stderr = execute(session, "api.help()")
    assert stderr == ""
    assert "snapshot" in stdout
    assert "heatmap_density" in stdout
