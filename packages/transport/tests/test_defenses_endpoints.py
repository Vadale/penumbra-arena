"""Integration tests for the Phase 5 Tier 3 defense endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from penumbra_core.arena import ArenaConfig
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_transport.api import build_app


def _client() -> TestClient:
    sim = Simulation.build(
        SimulationConfig(n_agents=8, arena=ArenaConfig(n_nodes=15)),
        bootstrap(42),
    )
    return TestClient(build_app(sim, tick_hz=200.0))


@pytest.mark.parametrize(
    "name",
    [
        "data_poisoning",
        "padding",
        "k_anonymity",
        "l_diversity",
        "gan",
        "request_obfuscation",
    ],
)
def test_defense_demo_returns_curve(name: str) -> None:
    """Every defense exposes an `available + curve` payload."""
    with _client() as client:
        response = client.get(f"/defenses/{name}/demo")
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is True
        assert isinstance(body["curve"], list)
        assert len(body["curve"]) >= 4


def test_padding_demo_includes_cover_schedule() -> None:
    with _client() as client:
        body = client.get("/defenses/padding/demo").json()
        assert "cover_schedule_preview" in body
        assert isinstance(body["cover_schedule_size"], int)
