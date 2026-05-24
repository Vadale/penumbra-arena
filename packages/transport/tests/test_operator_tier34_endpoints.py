"""Tier 3 + Tier 4 operator endpoints — round-trip smoke tests.

Concept taught: the 12 new ``POST /operator/{attack_*, defense_*}``
endpoints + ``GET /operator/defense_status`` are factory-built from
the shared ``_submit_and_drain`` plumbing. We assert (a) every kind is
reachable, (b) defense state is observable via the status endpoint,
(c) the ``operator.attack`` event flows through the orchestrator's bus.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from penumbra_core.arena import ArenaConfig
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_operator.actions import ATTACK_KINDS, DEFENSE_KINDS
from penumbra_transport.api import build_app


def _client() -> TestClient:
    sim = Simulation.build(
        SimulationConfig(n_agents=4, arena=ArenaConfig(n_nodes=15)),
        bootstrap(42),
    )
    return TestClient(build_app(sim, tick_hz=200.0))


def test_attack_endpoints_round_trip_envelope_and_emit_event() -> None:
    with _client() as client:
        assert client.post("/operator/enable").status_code == 200
        for kind in ATTACK_KINDS:
            payload = _payload_for(kind)
            res = client.post(f"/operator/{kind}", json=payload)
            assert res.status_code == 200, (kind, res.text)
            body = res.json()
            assert body["success"] is True, (kind, body)
            data = body["data"]
            assert "accepted" in data
            assert "evidence" in data
            assert "defender_response" in data
        # All attack events should have hit the orchestrator's bus.
        events = client.get("/events/recent").json()
        kinds_seen = {e["kind"] for e in events.get("events", events)}
        assert "operator.attack" in kinds_seen


def test_defense_endpoints_round_trip_and_status_reflects_config() -> None:
    with _client() as client:
        assert client.post("/operator/enable").status_code == 200
        # k-anonymity
        assert (
            client.post(
                "/operator/defense_k_anonymity",
                json={"k": 7, "statistic": "money_supply"},
            ).status_code
            == 200
        )
        # padding
        assert (
            client.post(
                "/operator/defense_padding",
                json={"kind": "response", "size": 2048},
            ).status_code
            == 200
        )
        # gan
        assert (
            client.post(
                "/operator/defense_gan_poison",
                json={"rate": 0.25, "target_stat": "price_index"},
            ).status_code
            == 200
        )
        # pause dp
        assert client.post("/operator/defense_pause_dp", json={}).status_code == 200
        # rotate keys
        assert client.post("/operator/defense_rotate_keys", json={}).status_code == 200

        status = client.get("/operator/defense_status").json()
        assert status["enabled"] is True
        assert status["k_anonymity"] == {"k": 7, "statistic": "money_supply"}
        assert status["padding"] == {"kind": "response", "size": 2048}
        assert status["gan_poison"] == {"rate": 0.25, "target_stat": "price_index"}
        assert status["dp_paused"] is True
        assert status["key_rotations"] == 1

        # Resume + query_dp should now succeed.
        assert client.post("/operator/defense_resume_dp", json={}).status_code == 200
        q = client.post(
            "/operator/query_dp",
            json={"statistic": "money_supply", "epsilon": 0.01},
        ).json()
        assert q["success"] is True


def test_defense_enable_krum_endpoint_fails_without_trainer() -> None:
    with _client() as client:
        assert client.post("/operator/enable").status_code == 200
        res = client.post("/operator/defense_enable_krum", json={"f": 2})
        body = res.json()
        # No FederatedTrainer attached -> structured failure inside the
        # OperatorActionResult envelope (endpoint itself is 200).
        assert res.status_code == 200
        assert body["success"] is False
        assert body["error"]["code"] == "no_trainer"


def _payload_for(kind: str) -> dict[str, object]:
    if kind == "attack_replay":
        return {"target_signature_hex": "ab" * 8, "replay_offset": 0}
    if kind == "attack_byzantine":
        return {"n_equivocations": 1}
    if kind == "attack_dp_recon":
        return {"target_agent": 0, "query_log": [{"q": i} for i in range(8)]}
    if kind == "attack_linkability":
        return {"feature_set": ["mean_pos"], "target_agent": 0}
    if kind == "attack_membership":
        return {"target_observation": [0.1, 0.2, 0.3]}
    if kind == "attack_snark_forge":
        return {"circuit": "legal_path"}
    raise AssertionError(f"no payload for {kind}")


def test_every_advertised_kind_has_endpoint() -> None:
    """Smoke: every ATTACK_KINDS + DEFENSE_KINDS entry has a POST handler."""
    with _client() as client:
        assert client.post("/operator/enable").status_code == 200
        # We just check the route exists (a 200 or 422 means the route
        # is mounted; a 404 would mean the factory missed a kind).
        for kind in (*ATTACK_KINDS, *DEFENSE_KINDS):
            res = client.post(f"/operator/{kind}", json={})
            assert res.status_code != 404, kind
