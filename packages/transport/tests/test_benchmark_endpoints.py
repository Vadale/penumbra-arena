"""Endpoint tests for the Penumbra-Bench Tier 2 public leaderboard.

Concept taught: the leaderboard endpoint reads `state/bench/*.json`
files directly off disk; we don't mock the filesystem, we rely on
the real shipped tiny-tier submissions to validate the contract.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from penumbra_core.arena import ArenaConfig
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_transport.api import build_app


def _build_test_app():
    sim = Simulation.build(
        SimulationConfig(n_agents=8, arena=ArenaConfig(n_nodes=15)),
        bootstrap(42),
    )
    return build_app(sim, tick_hz=200.0)


def test_benchmark_leaderboard_returns_list_filtered_by_tier() -> None:
    with TestClient(_build_test_app()) as client:
        body = client.get("/benchmark/leaderboard", params={"tier": "tiny"}).json()
        assert body["available"] is True
        assert body["tier"] == "tiny"
        assert isinstance(body["entries"], list)
        assert len(body["entries"]) >= 1
        for entry in body["entries"]:
            assert entry["tier"] == "tiny"
            assert "composite_score" in entry
            assert "task_scores" in entry
            assert isinstance(entry["task_scores"], dict)


def test_benchmark_leaderboard_sorted_by_composite_desc() -> None:
    with TestClient(_build_test_app()) as client:
        body = client.get("/benchmark/leaderboard", params={"tier": "tiny"}).json()
        scores = [float(e["composite_score"]) for e in body["entries"]]
        assert scores == sorted(scores, reverse=True)
        ranks = [int(e["rank"]) for e in body["entries"]]
        assert ranks == list(range(1, len(ranks) + 1))


def test_benchmark_leaderboard_empty_for_tier_with_no_submissions() -> None:
    with TestClient(_build_test_app()) as client:
        body = client.get("/benchmark/leaderboard", params={"tier": "large"}).json()
        assert body["available"] is True
        assert body["tier"] == "large"
        assert body["entries"] == []
        assert body["n_total"] == 0


def test_benchmark_leaderboard_rejects_unknown_tier() -> None:
    with TestClient(_build_test_app()) as client:
        resp = client.get("/benchmark/leaderboard", params={"tier": "huge"})
        assert resp.status_code == 400


def test_benchmark_leaderboard_respects_limit() -> None:
    with TestClient(_build_test_app()) as client:
        body = client.get("/benchmark/leaderboard", params={"tier": "tiny", "limit": 2}).json()
        assert len(body["entries"]) <= 2


def test_benchmark_submission_returns_full_detail() -> None:
    with TestClient(_build_test_app()) as client:
        # Use a known shipped submission.
        body = client.get("/benchmark/submission/random-walk-tiny.json").json()
        assert body["available"] is True
        assert body["filename"] == "random-walk-tiny.json"
        assert body["tier"] == "tiny"
        assert "tasks" in body
        assert "composite_score" in body
        assert "penumbra_commit" in body


def test_benchmark_submission_rejects_path_traversal() -> None:
    with TestClient(_build_test_app()) as client:
        resp = client.get("/benchmark/submission/..%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 404)


def test_benchmark_submission_404_for_unknown() -> None:
    with TestClient(_build_test_app()) as client:
        resp = client.get("/benchmark/submission/does-not-exist.json")
        assert resp.status_code == 404
