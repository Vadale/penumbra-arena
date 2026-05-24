"""Integration tests for the Phase 5 Tier 2 attack-suite endpoints."""

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
        "agent_fingerprint",
        "trajectory_fingerprint",
        "membership_inference",
        "model_inversion",
        "reward_poisoning",
    ],
)
def test_attack_demo_returns_available_envelope(name: str) -> None:
    with _client() as client:
        response = client.get(f"/attacks/{name}/demo")
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is True
        assert "defence_hint" in body


def test_cache_sidechannel_endpoint_runs() -> None:
    with _client() as client:
        response = client.get("/attacks/cache_sidechannel/demo")
        assert response.status_code == 200
        body = response.json()
        # If TenSEAL unavailable the demo cleanly reports available=False.
        if body["available"]:
            assert "leak_detected" in body
            assert "welch_t" in body
