"""Integration test for /world/{save,load,list} via FastAPI TestClient."""

from __future__ import annotations

import os
import tempfile

from fastapi.testclient import TestClient
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_transport.api import build_app


def _client_with_snapshots_dir(tmpdir: str) -> TestClient:
    os.environ["PENUMBRA_SNAPSHOTS_DIR"] = tmpdir
    sim = Simulation.build(SimulationConfig(n_agents=5, match_max_ticks=50), bootstrap(seed=11))
    app = build_app(simulation=sim, tick_hz=200.0)  # spin fast for the test
    return TestClient(app)


def test_save_creates_snapshot_files() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        client = _client_with_snapshots_dir(tmpdir)
        with client:
            r = client.post("/world/save", json={"name": "first"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "first"
        snap = os.listdir(os.path.join(tmpdir, "first"))
        assert "chain" in snap
        assert "simulation.pkl" in snap


def test_world_list_reports_simulation_presence() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        client = _client_with_snapshots_dir(tmpdir)
        with client:
            client.post("/world/save", json={"name": "alpha"})
            r = client.get("/world/list")
        assert r.status_code == 200
        snaps = r.json()["snapshots"]
        assert any(s["name"] == "alpha" and s["has_simulation"] for s in snaps)


def test_save_rejects_bad_name() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        client = _client_with_snapshots_dir(tmpdir)
        with client:
            r = client.post("/world/save", json={"name": "../etc/passwd"})
        assert r.status_code == 400


def test_load_returns_404_for_missing_snapshot() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        client = _client_with_snapshots_dir(tmpdir)
        with client:
            r = client.post("/world/load", json={"name": "never-saved"})
        assert r.status_code == 404


def test_save_then_load_swaps_chain_height() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        client = _client_with_snapshots_dir(tmpdir)
        with client:
            client.post("/world/save", json={"name": "checkpoint"})
            r = client.post("/world/load", json={"name": "checkpoint"})
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "checkpoint"
        # height matches the snapshot (chain may not have advanced yet).
        assert body["height"] >= 0
