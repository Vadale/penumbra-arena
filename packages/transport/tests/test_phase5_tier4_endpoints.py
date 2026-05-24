"""Phase 5 Tier 4 endpoints: /attacker/policy*, /ctf/*, /world/branch*."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_transport.api import build_app


@pytest.fixture
def client() -> TestClient:
    tmp = tempfile.mkdtemp(prefix="penumbra-t4-")
    os.environ["PENUMBRA_SNAPSHOTS_DIR"] = tmp
    sim = Simulation.build(SimulationConfig(n_agents=4, match_max_ticks=50), bootstrap(seed=3))
    app = build_app(simulation=sim, tick_hz=200.0)
    return TestClient(app)


def test_attacker_policy_register_list_delete(client: TestClient) -> None:
    with client:
        r = client.post(
            "/attacker/policy",
            json={
                "name": "endpoint_demo",
                "code": "def policy(s, o):\n    return 1\n",
                "scope": "all",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "endpoint_demo"
        assert body["try"]["ok"] is True
        listing = client.get("/attacker/policies").json()
        assert any(p["name"] == "endpoint_demo" for p in listing["policies"])
        gone = client.delete("/attacker/policy/endpoint_demo")
        assert gone.status_code == 200
        missing = client.delete("/attacker/policy/endpoint_demo")
        assert missing.status_code == 404


def test_attacker_policy_rejects_forbidden_source(client: TestClient) -> None:
    with client:
        r = client.post(
            "/attacker/policy",
            json={"name": "bad", "code": "import os\ndef policy(s, o):\n    return 0\n"},
        )
        assert r.status_code == 400


def test_ctf_list_and_submit_wrong_flag(client: TestClient) -> None:
    with client:
        r = client.get("/ctf/challenges")
        assert r.status_code == 200
        challenges = r.json()["challenges"]
        assert any(c["id"] == "ctf-dp-recon-001" for c in challenges)
        submission = client.post(
            "/ctf/submit/ctf-dp-recon-001",
            json={"flag": "PEN{nope}", "session_id": "tester"},
        )
        assert submission.status_code == 200
        assert submission.json()["correct"] is False


def test_ctf_submit_correct_flag_appears_on_leaderboard(client: TestClient) -> None:
    from penumbra_ctf import global_registry

    expected = global_registry().challenges["ctf-linkability-002"].expected_flag()
    with client:
        r = client.post(
            "/ctf/submit/ctf-linkability-002",
            json={"flag": expected, "session_id": "tester-ok"},
        )
        assert r.status_code == 200
        assert r.json()["correct"] is True
        board = client.get("/ctf/leaderboard/ctf-linkability-002").json()
        assert any(row["session_id"] == "tester-ok" for row in board["leaderboard"])


def test_ctf_unknown_challenge_returns_404(client: TestClient) -> None:
    with client:
        r = client.post("/ctf/submit/none-such", json={"flag": "x", "session_id": "s"})
        assert r.status_code == 404
        r = client.get("/ctf/leaderboard/none-such")
        assert r.status_code == 404


def test_world_branch_create_list_advance_compare(client: TestClient) -> None:
    with client:
        r = client.post("/world/branch", json={"name": "expA", "n_branches": 2})
        assert r.status_code == 200, r.text
        ids = r.json()["branch_ids"]
        assert ids == ["expA-1", "expA-2"]
        listed = client.get("/world/branches").json()
        assert len(listed["branches"]) >= 2
        adv = client.post(f"/world/branch/{ids[0]}/advance", json={"ticks": 2})
        assert adv.status_code == 200
        cmp_r = client.post("/world/branches/compare", json={"branch_ids": ids})
        assert cmp_r.status_code == 200
        rows = cmp_r.json()["branches"]
        assert {row["branch_id"] for row in rows} == set(ids)


def test_world_branch_unknown_returns_404(client: TestClient) -> None:
    with client:
        r = client.post("/world/branch/nope-1/advance", json={"ticks": 1})
        assert r.status_code == 404
        r = client.post("/world/branches/compare", json={"branch_ids": ["nope-1"]})
        assert r.status_code == 404
