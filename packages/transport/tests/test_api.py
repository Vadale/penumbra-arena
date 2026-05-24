"""Integration tests for the FastAPI app."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from penumbra_core.arena import ArenaConfig
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_transport.api import build_app
from penumbra_transport.framing import decode_frame


def _build_test_app():
    sim = Simulation.build(
        SimulationConfig(n_agents=8, arena=ArenaConfig(n_nodes=15)),
        bootstrap(42),
    )
    return build_app(sim, tick_hz=200.0)  # fast ticks so tests don't drag


def test_health_endpoint() -> None:
    with TestClient(_build_test_app()) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["match_id"] >= 0
        assert "uptime_seconds" in body


def test_state_endpoint() -> None:
    with TestClient(_build_test_app()) as client:
        response = client.get("/state")
        assert response.status_code == 200
        body = response.json()
        assert body["arena_edge_count"] > 0
        assert len(body["agent_positions"]) == 8


def test_pause_resume_step_controls() -> None:
    with TestClient(_build_test_app()) as client:
        assert client.post("/control/pause").json() == {"state": "paused"}
        before = client.get("/health").json()["tick"]
        step_response = client.post("/control/step").json()
        assert step_response["tick"] == before + 1
        assert client.post("/control/resume").json() == {"state": "running"}


def test_time_warp_validation() -> None:
    with TestClient(_build_test_app()) as client:
        assert client.post("/control/time-warp/5").json() == {"time_warp": 5}
        assert client.post("/control/time-warp/0").status_code == 400
        assert client.post("/control/time-warp/101").status_code == 400


def test_get_tick_hz_exposes_live_value_and_ladder() -> None:
    with TestClient(_build_test_app()) as client:
        body = client.get("/control/tick_hz").json()
        assert "tick_hz" in body
        assert body["tick_hz"] == pytest.approx(200.0)  # test app uses 200 Hz
        assert body["allowed"] == [0.5, 1.0, 2.0, 5.0, 10.0]


def test_post_tick_hz_updates_loop_period() -> None:
    with TestClient(_build_test_app()) as client:
        ok = client.post("/control/tick_hz", json={"tick_hz": 5.0})
        assert ok.status_code == 200
        assert ok.json()["tick_hz"] == pytest.approx(5.0)
        # GET should now reflect the new value.
        assert client.get("/control/tick_hz").json()["tick_hz"] == pytest.approx(5.0)


def test_post_tick_hz_rejects_disallowed_values() -> None:
    with TestClient(_build_test_app()) as client:
        bad = client.post("/control/tick_hz", json={"tick_hz": 17.0})
        assert bad.status_code == 400
        missing = client.post("/control/tick_hz", json={})
        assert missing.status_code == 400


def test_websocket_streams_frames() -> None:
    """Connect, receive a frame, decode it."""
    with TestClient(_build_test_app()) as client, client.websocket_connect("/ws") as ws:
        blob = ws.receive_bytes()
        payload = decode_frame(blob)
        assert "tick" in payload
        assert "agent_positions" in payload


@pytest.mark.asyncio
async def test_concurrent_subscribers_dont_starve_each_other() -> None:
    """Two clients each receive at least one frame within a reasonable budget."""
    with (
        TestClient(_build_test_app()) as client,
        client.websocket_connect("/ws") as a,
        client.websocket_connect("/ws") as b,
    ):
        a_blob = a.receive_bytes()
        b_blob = b.receive_bytes()
        assert decode_frame(a_blob)["tick"] >= 0
        assert decode_frame(b_blob)["tick"] >= 0
    # asyncio import kept to mark the function async; no specific await needed
    await asyncio.sleep(0)
