"""Save-resume endpoints — banner / resume / discard round trips.

Concept taught: the three new ``/operator/sessions/{resumable,resume,
discard}`` endpoints wrap the save-resume layer. We assert the
videogame UX contract end-to-end against a TestClient: start a
scenario, take an action, kill the client, spin a fresh client
sharing the same on-disk save dir, hit ``resumable`` (banner) →
``resume`` (hot-swap) and confirm the orchestrator's simulation
tick is exactly the saved value (NOT advanced).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from penumbra_core.arena import ArenaConfig
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_transport.api import build_app


def _client(tmp_path: Path) -> TestClient:
    sim = Simulation.build(
        SimulationConfig(n_agents=4, arena=ArenaConfig(n_nodes=15)),
        bootstrap(42),
    )
    app = build_app(sim, tick_hz=200.0)
    app.state.operator_save_dir = tmp_path
    return TestClient(app)


def _start_scenario(
    client: TestClient, scenario_id: str = "scn-009-trade-bot-market-maker"
) -> None:
    assert client.post("/operator/enable").status_code == 200
    resp = client.post(f"/operator/scenarios/{scenario_id}/start")
    assert resp.status_code == 200, resp.text


def test_resumable_returns_unavailable_when_no_session(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.get("/operator/sessions/resumable").json()
        assert body == {"available": False}


def test_save_resume_round_trip(tmp_path: Path) -> None:
    """Start scenario, take 2 actions, drop runner, re-instantiate, resume."""
    scenario_id = "scn-009-trade-bot-market-maker"

    with _client(tmp_path) as client:
        _start_scenario(client, scenario_id)
        # Two actions: a no-op move (operator already on first node) +
        # a buy. Both run through _submit_and_drain → save_session.
        client.post("/operator/move", json={"target_node": 0})
        client.post("/operator/buy", json={"product": "0", "qty": 0})
        banner = client.get("/operator/sessions/resumable").json()
        assert banner["available"] is True
        assert banner["scenario_id"] == scenario_id
        saved_tick = int(banner["saved_at_tick"])

    # Spawn a fresh app process (TestClient lifespan): the orchestrator
    # is brand new but the save_dir is shared, so resume should hot-
    # swap the snapshotted sim in.
    with _client(tmp_path) as client2:
        body = client2.get("/operator/sessions/resumable").json()
        assert body["available"] is True
        resumed = client2.post("/operator/sessions/resume")
        assert resumed.status_code == 200, resumed.text
        payload = resumed.json()
        assert payload["resumed"] is True
        assert payload["scenario_id"] == scenario_id
        # The clock paused: resumed tick equals the saved tick (no
        # wall-clock fast-forward).
        assert payload["tick"] == saved_tick
        # And the operator scenario runner now knows about the
        # restored session — status endpoint reports active=True.
        client2.post("/operator/enable")
        status = client2.get(f"/operator/scenarios/{scenario_id}/status").json()
        assert status["active"] is True


def test_save_resume_preserves_world_state(tmp_path: Path) -> None:
    """Saved sim.tick matches restored sim.tick down to the integer."""
    scenario_id = "scn-009-trade-bot-market-maker"
    with _client(tmp_path) as client:
        _start_scenario(client, scenario_id)
        client.post("/operator/move", json={"target_node": 0})
        banner_a = client.get("/operator/sessions/resumable").json()
        # Perturb the live sim AFTER save: more actions, more ticks.
        client.post("/operator/buy", json={"product": "0", "qty": 0})
        client.post("/operator/sell", json={"product": "0", "qty": 0})
        # The latest save reflects the latest perturbation.
        banner_b = client.get("/operator/sessions/resumable").json()
        # Tick should be monotonically non-decreasing across saves.
        assert banner_b["saved_at_tick"] >= banner_a["saved_at_tick"]
        latest_saved_tick = int(banner_b["saved_at_tick"])

    with _client(tmp_path) as client2:
        client2.post("/operator/sessions/resume")
        # Status reports the same tick the save was taken at — NOT a
        # fresh-boot tick (which would be 0 or whatever the lifespan
        # advanced to before the resume call).
        client2.post("/operator/enable")
        status = client2.get(f"/operator/scenarios/{scenario_id}/status").json()
        assert status["active"] is True
        # elapsed_ticks = current - start_tick; both came from the
        # restored ScenarioSession + Simulation, so the relation is
        # preserved across the round-trip.
        assert status["elapsed_ticks"] >= 0
        # Hot-swapped simulation tick matches the saved value.
        state = client2.get("/state").json()
        assert state["tick"] == latest_saved_tick


def test_discard_removes_active_json(tmp_path: Path) -> None:
    scenario_id = "scn-009-trade-bot-market-maker"
    with _client(tmp_path) as client:
        _start_scenario(client, scenario_id)
        client.post("/operator/move", json={"target_node": 0})
        assert client.get("/operator/sessions/resumable").json()["available"] is True
        result = client.post("/operator/sessions/discard").json()
        assert result["discarded"] is True
        assert client.get("/operator/sessions/resumable").json() == {"available": False}


def test_abandon_clears_session(tmp_path: Path) -> None:
    scenario_id = "scn-009-trade-bot-market-maker"
    with _client(tmp_path) as client:
        _start_scenario(client, scenario_id)
        client.post("/operator/move", json={"target_node": 0})
        assert client.get("/operator/sessions/resumable").json()["available"] is True
        client.post(f"/operator/scenarios/{scenario_id}/abandon")
        assert client.get("/operator/sessions/resumable").json() == {"available": False}


def test_resume_with_no_save_returns_404(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        resp = client.post("/operator/sessions/resume")
        assert resp.status_code == 404


def test_terminal_status_clears_active_pointer(tmp_path: Path) -> None:
    """When victory or failure trips, the banner stops surfacing the save."""
    scenario_id = "scn-009-trade-bot-market-maker"
    with _client(tmp_path) as client:
        _start_scenario(client, scenario_id)
        client.post("/operator/move", json={"target_node": 0})
        assert client.get("/operator/sessions/resumable").json()["available"] is True
        # Force failure: wipe the operator's wallet below the
        # ``operator.coins < 0`` threshold. Reach through app.state
        # the same way build_app's endpoints do; the TestClient
        # ``app`` attribute exposes the FastAPI instance at runtime
        # even though Starlette's type stubs hide it.
        app_obj: object = client.app  # type: ignore[attr-defined]
        orch = app_obj.state.penumbra.orchestrator  # type: ignore[attr-defined]
        wallet = orch.market.wallets[orch.operator_context.operator_agent_id]
        wallet.coins = -100.0
        status = client.get(f"/operator/scenarios/{scenario_id}/status").json()
        assert status["failure_met"] is True
        # After a terminal status poll, the banner is gone.
        assert client.get("/operator/sessions/resumable").json() == {"available": False}


@pytest.mark.parametrize(
    "scenario_id",
    [
        "scn-001-bullwhip-defender",
        "scn-002-dp-recon-attacker",
        "scn-003-byzantine-validator",
        "scn-004-replay-the-leader",
        "scn-005-linkability-attacker",
        "scn-006-membership-inference-defender",
        "scn-007-fl-backdoor-injector",
        "scn-008-fl-backdoor-detector",
        "scn-009-trade-bot-market-maker",
        "scn-010-snark-forge-attempt",
        "scn-011-cross-pillar-defender",
        "scn-012-zero-day-improv",
    ],
)
def test_no_wall_clock_failure_clauses(scenario_id: str) -> None:
    """All 12 starter scenarios use sim-tick predicates only (no wall-clock).

    Documents that save-resume's sim-tick time semantics are safe: no
    scenario YAML ships a clause keyed on wall time, so resuming from
    a saved tick never causes a failure-clause re-evaluation that the
    player would not have triggered in a wall-clock-continuous run.
    """
    from penumbra_operator.scenarios import load_scenarios

    scenarios = {s.id: s for s in load_scenarios()}
    scn = scenarios[scenario_id]
    for clause in (*scn.victory, *scn.failure):
        for forbidden in ("wall", "seconds", "minutes", "hours", "wallclock"):
            assert forbidden not in clause.lower(), (scenario_id, clause)
