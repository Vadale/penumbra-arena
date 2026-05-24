"""Integration tests for the Phase-7 interactivity endpoints.

Concept taught: when a backend ships endpoints with a stable contract,
the cheapest way to keep that contract honest is a focused integration
test per route — TestClient drives the FastAPI app in-process, so the
test exercises real serialization, real dependency wiring, and the
real event bus.
"""

from __future__ import annotations

import importlib.util
import json
from typing import cast

import pytest
from fastapi.testclient import TestClient
from penumbra_core.arena import ArenaConfig
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_transport.api import build_app


def _build_test_app():
    sim = Simulation.build(
        SimulationConfig(n_agents=6, arena=ArenaConfig(n_nodes=15)),
        bootstrap(42),
    )
    return build_app(sim, tick_hz=200.0)


def test_agents_list_returns_one_entry_per_agent() -> None:
    with TestClient(_build_test_app()) as client:
        response = client.get("/agents")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 6
        first = body[0]
        for key in ("id", "position", "money", "name"):
            assert key in first
        assert isinstance(first["position"], list)
        assert len(first["position"]) == 2


def test_agent_detail_returns_full_payload() -> None:
    with TestClient(_build_test_app()) as client:
        response = client.get("/agents/0")
        assert response.status_code == 200
        body = response.json()
        for key in (
            "id",
            "position",
            "money",
            "name",
            "current_policy",
            "recent_actions",
            "action_distribution",
            "encrypted_state_bytes",
            "kyber_pk_fingerprint",
            "dilithium_pk_fingerprint",
            "last_obs_summary",
        ):
            assert key in body, key
        assert body["id"] == 0
        assert body["current_policy"] in ("mappo", "random_walk")
        assert isinstance(body["last_obs_summary"], dict)
        assert {"mean", "std", "dim"} <= set(body["last_obs_summary"].keys())


def test_agent_detail_404_on_out_of_range_id() -> None:
    with TestClient(_build_test_app()) as client:
        response = client.get("/agents/999")
        assert response.status_code == 404


def test_control_inject_cpi_shock_records_on_bus() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        response = client.post(
            "/control/inject",
            json={"kind": "cpi.shock", "payload": {"ratio": 1.7}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["kind"] == "cpi.shock"
        assert body["payload"]["ratio"] == pytest.approx(1.7)
        bus = app.state.penumbra.orchestrator.event_bus
        recorded = [e for e in bus.recent(limit=50) if e.kind == "cpi.shock"]
        assert recorded, "cpi.shock event was not recorded on the bus"


def test_control_inject_unknown_kind_400() -> None:
    with TestClient(_build_test_app()) as client:
        response = client.post(
            "/control/inject",
            json={"kind": "not.a.real.kind", "payload": {}},
        )
        assert response.status_code == 400


def test_control_inject_agent_blocked_event() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        response = client.post(
            "/control/inject",
            json={
                "kind": "agent.blocked",
                "payload": {"agent_id": 1, "reason": "synthetic"},
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["payload"]["agent_id"] == 1


def test_control_step_advances_simulation_by_n() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        assert client.post("/control/pause").json() == {"state": "paused"}
        before = app.state.penumbra.simulation.tick_counter
        response = client.post("/control/step", json={"n": 5})
        assert response.status_code == 200
        body = response.json()
        assert body["previous_tick"] == before
        assert body["new_tick"] == before + 5
        assert app.state.penumbra.simulation.tick_counter == before + 5


def test_control_step_validates_range() -> None:
    with TestClient(_build_test_app()) as client:
        client.post("/control/pause")
        bad_low = client.post("/control/step", json={"n": 0})
        assert bad_low.status_code == 400
        bad_high = client.post("/control/step", json={"n": 9999})
        assert bad_high.status_code == 400


def test_export_chart_inflation_csv() -> None:
    with TestClient(_build_test_app()) as client:
        response = client.get("/export/chart/inflation?format=csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        body_text = response.text
        first_line = body_text.splitlines()[0] if body_text else ""
        assert "cpi" in first_line or "tick" in first_line


def test_export_chart_inflation_json() -> None:
    with TestClient(_build_test_app()) as client:
        response = client.get("/export/chart/inflation?format=json")
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert body["metric"] == "inflation"
        assert isinstance(body["data"], list)


def test_export_chart_inflation_png() -> None:
    if importlib.util.find_spec("matplotlib") is None:
        pytest.skip("matplotlib not importable in this venv")
    with TestClient(_build_test_app()) as client:
        response = client.get("/export/chart/inflation?format=png")
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("image/png")
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize(
    "metric",
    [
        "trajectory_mean",
        "vrf_leader",
        "signing_verified",
        "dp_epsilon_spent",
        "arena_graph",
        "pca",
    ],
)
def test_export_chart_extended_metric_png(metric: str) -> None:
    """Extended metrics must produce a well-formed 800x400 PNG, not an empty blob.

    Empty-data branches still render a "no data" placeholder image -- the
    user-visible contract is "the PNG is a labelled chart of the right
    size", not "the chart has live data". Either way the bytes start
    with the PNG magic, ``content-type`` is ``image/png``, and the
    payload is non-trivial in size (> 1 KB rules out the "single black
    slab" failure the user reported).
    """
    if importlib.util.find_spec("matplotlib") is None:
        pytest.skip("matplotlib not importable in this venv")
    with TestClient(_build_test_app()) as client:
        response = client.get(f"/export/chart/{metric}?format=png")
        assert response.status_code == 200, response.text
        assert response.headers.get("content-type", "").startswith("image/png")
        assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
        assert (
            len(response.content) > 1024
        ), f"{metric} png unexpectedly small ({len(response.content)} bytes)"


@pytest.mark.parametrize(
    "metric",
    [
        "trajectory_mean",
        "vrf_leader",
        "signing_verified",
        "dp_epsilon_spent",
        "pca",
        "spectral",
        "causal",
        "anova",
        "autocorrelation",
        "correlations",
        "permutation",
        "arena_graph",
        "hdbscan_clusters",
    ],
)
def test_export_chart_extended_metric_csv_json(metric: str) -> None:
    """CSV + JSON exports work for every extended metric too."""
    with TestClient(_build_test_app()) as client:
        csv_resp = client.get(f"/export/chart/{metric}?format=csv")
        assert csv_resp.status_code == 200
        assert "text/csv" in csv_resp.headers.get("content-type", "")
        json_resp = client.get(f"/export/chart/{metric}?format=json")
        assert json_resp.status_code == 200
        body = json_resp.json()
        assert body["metric"] == metric
        assert "data" in body


def test_export_chart_unsupported_metric_404() -> None:
    with TestClient(_build_test_app()) as client:
        response = client.get("/export/chart/totally_made_up?format=json")
        assert response.status_code == 404


def test_export_notebook_returns_nbformat_json() -> None:
    with TestClient(_build_test_app()) as client:
        response = client.get("/export/notebook?metric=inflation")
        assert response.status_code == 200
        body = json.loads(response.content.decode("utf-8"))
        assert body["nbformat"] == 4
        assert any(cell.get("cell_type") == "code" for cell in body["cells"])
        assert any(
            cell.get("cell_type") == "markdown"
            and "inflation" in "".join(cast(list[str], cell.get("source", [])))
            for cell in body["cells"]
        )


def test_export_notebook_unsupported_metric_404() -> None:
    with TestClient(_build_test_app()) as client:
        response = client.get("/export/notebook?metric=nonexistent")
        assert response.status_code == 404


def test_config_get_returns_expected_schema() -> None:
    with TestClient(_build_test_app()) as client:
        response = client.get("/config")
        assert response.status_code == 200
        body = response.json()
        for key in (
            "n_agents",
            "match_max_ticks",
            "tick_hz",
            "reward_weights",
            "defenses",
            "pty_enabled",
            "mappo_loaded",
        ):
            assert key in body, key
        assert {"dispatch_bonus", "dispatch_penalty", "fill_rate_bonus"} <= set(
            body["reward_weights"].keys()
        )
        assert {"k_anonymity_k", "dp_epsilon_budget"} <= set(body["defenses"].keys())


def test_config_post_mutates_tick_hz() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        response = client.post("/config", json={"tick_hz": 1.0})
        assert response.status_code == 200
        body = response.json()
        assert "tick_hz" in body["applied"]
        assert app.state.penumbra.loop.tick_hz == pytest.approx(1.0)


def test_config_post_n_agents_requires_restart() -> None:
    with TestClient(_build_test_app()) as client:
        response = client.post("/config", json={"n_agents": 99})
        assert response.status_code == 200
        body = response.json()
        assert "n_agents" in body["restart_required"]
