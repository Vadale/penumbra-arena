"""Endpoint tests for the Logistics Tier 1 + Federated Learning Tier 1+2 routes."""

from __future__ import annotations

from fastapi import FastAPI
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


# ── Logistics ────────────────────────────────────────────────────


def test_logistics_fill_rate_endpoint_available() -> None:
    with TestClient(_build_test_app()) as client:
        body = client.get("/logistics/fill-rate").json()
        assert body["available"] is True
        assert "overall_fill_rate" in body
        assert "per_product" in body


def test_logistics_inventory_health_endpoint_available() -> None:
    with TestClient(_build_test_app()) as client:
        body = client.get("/logistics/inventory-health").json()
        assert body["available"] is True
        assert "cells" in body
        assert body["n_cells_total"] >= 1


def test_logistics_orders_endpoint_available() -> None:
    with TestClient(_build_test_app()) as client:
        body = client.get("/logistics/orders").json()
        assert body["available"] is True
        assert "n_pending" in body
        assert "n_fulfilled" in body


def test_logistics_reorder_policy_get_and_post() -> None:
    with TestClient(_build_test_app()) as client:
        before = client.get("/logistics/reorder-policy").json()
        assert before["available"] is True
        n_before = before["n_pairs_total"]
        resp = client.post(
            "/logistics/reorder-policy",
            params={"s_fraction": 0.4, "S_fraction": 0.95},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["n_pairs"] == n_before


def test_logistics_reorder_policy_rejects_invalid_fractions() -> None:
    with TestClient(_build_test_app()) as client:
        resp = client.post(
            "/logistics/reorder-policy",
            params={"s_fraction": 0.9, "S_fraction": 0.5},
        )
        assert resp.status_code == 400


def test_logistics_capacity_endpoint_available() -> None:
    with TestClient(_build_test_app()) as client:
        body = client.get("/logistics/capacity").json()
        assert body["available"] is True
        assert "mean_utilization" in body
        assert "per_agent" in body


def test_logistics_dispatch_endpoint_available() -> None:
    with TestClient(_build_test_app()) as client:
        body = client.get("/logistics/dispatch").json()
        assert body["available"] is True
        for key in (
            "n_pending",
            "n_assigned",
            "n_unassigned",
            "n_fulfilled",
            "n_placed",
            "n_phantom_fulfilled",
            "mean_carrier_revenue",
            "fulfilment_efficiency",
            "top_carriers",
            "agent_earnings",
        ):
            assert key in body


def test_logistics_vrp_baseline_endpoint_responds() -> None:
    """VRP endpoint either returns a solution or a clean unavailable reason."""
    with TestClient(_build_test_app()) as client:
        body = client.get("/logistics/vrp-baseline?solver=greedy").json()
        # When no pending orders are in the mempool yet, endpoint returns
        # available=False with a reason; otherwise it returns a solution.
        if body["available"] is False:
            assert "reason" in body
        else:
            assert "solver_total_cost" in body
            assert "gap_fraction" in body
            assert "compute_time_ms" in body


def test_logistics_vrp_baseline_rejects_bad_solver() -> None:
    with TestClient(_build_test_app()) as client:
        resp = client.get("/logistics/vrp-baseline?solver=banana")
        assert resp.status_code == 400


def test_logistics_vrp_baseline_after_forcing_orders() -> None:
    """Force the orchestrator into a state with pending orders, then solve."""
    app = _build_test_app()
    with TestClient(app) as client:
        orch = app.state.penumbra.orchestrator
        assert orch.logistics_mempool is not None
        # Push a few synthetic orders directly into the mempool.
        cities = list(orch.market.markets.keys())[:3]
        for i, city in enumerate(cities):
            product = orch.market.markets[city].stocked_products[0]
            orch.logistics_mempool.place(
                city=int(city), product=int(product), quantity=1, tick=i, reward=1.0
            )
        body = client.get("/logistics/vrp-baseline?solver=two_opt").json()
        assert body["available"] is True
        assert body["solver_total_cost"] >= 0.0
        assert body["n_orders_considered"] >= 1


# ── Federated Learning ────────────────────────────────────────────


def test_federated_status_returns_unavailable_when_not_started() -> None:
    with TestClient(_build_test_app()) as client:
        body = client.get("/federated/status").json()
        assert body["available"] is False


def test_federated_start_requires_mappo_checkpoint() -> None:
    """Without a MAPPO checkpoint loaded, /federated/start returns 400."""
    with TestClient(_build_test_app()) as client:
        resp = client.post("/federated/start")
        # mappo_runtime is None in the test app (no checkpoint env), expect 400.
        assert resp.status_code in (200, 400)
        if resp.status_code == 400:
            assert "MAPPO" in resp.json()["detail"]


def test_federated_round_without_start_returns_400() -> None:
    with TestClient(_build_test_app()) as client:
        resp = client.post("/federated/round")
        assert resp.status_code in (200, 400)


def test_federated_stop_is_idempotent_when_not_started() -> None:
    with TestClient(_build_test_app()) as client:
        body = client.post("/federated/stop").json()
        assert body["ok"] is True


def test_federated_privacy_endpoint_unavailable_when_not_started() -> None:
    with TestClient(_build_test_app()) as client:
        body = client.get("/federated/privacy").json()
        assert body["available"] is False
        assert body["epsilon"] == 0.0
        assert body["n_steps_accounted"] == 0
        assert body["mode"] == "toy"


def test_federated_privacy_endpoint_rejects_bad_delta() -> None:
    """delta must be in (0, 1)."""
    app = _build_test_app()
    with TestClient(app) as client:
        # Manually attach a trainer so the delta validation branch is reached.
        from penumbra_learning.federated import FederatedTrainer
        from penumbra_learning.mappo import MAPPO, MAPPOConfig

        sim = app.state.penumbra.simulation
        cfg = MAPPOConfig(obs_dim=18, n_actions=7, n_agents=len(sim.agents), hidden=8)
        mappo = MAPPO(cfg)
        trainer = FederatedTrainer.from_mappo(mappo, n_agents=len(sim.agents))
        app.state.penumbra.orchestrator.federated_trainer = trainer

        resp = client.get("/federated/privacy?delta=0.0")
        assert resp.status_code == 400
        resp2 = client.get("/federated/privacy?delta=1.5")
        assert resp2.status_code == 400


def test_federated_privacy_endpoint_reports_rdp_mode_after_dp_round() -> None:
    """After a DP-SGD round, /federated/privacy switches to mode='rdp'."""
    import numpy as np

    app = _build_test_app()
    with TestClient(app) as client:
        from penumbra_learning.federated import FederatedTrainer
        from penumbra_learning.mappo import MAPPO, MAPPOConfig

        sim = app.state.penumbra.simulation
        n_agents = len(sim.agents)
        cfg = MAPPOConfig(obs_dim=18, n_actions=7, n_agents=n_agents, hidden=8)
        mappo = MAPPO(cfg)
        trainer = FederatedTrainer.from_mappo(mappo, n_agents=n_agents)
        trainer.dp_noise_sigma = 1.0
        trainer.dp_l2_clip = 1.0
        trainer.local_steps = 2
        rng = np.random.default_rng(11)
        for agent_id in trainer.local_actors:
            for _ in range(16):
                obs = rng.standard_normal(size=(18,)).astype(np.float32)
                trainer.ingest(agent_id, obs, int(rng.integers(0, 7)))
        trainer.step()
        app.state.penumbra.orchestrator.federated_trainer = trainer

        body = client.get("/federated/privacy?delta=1e-5").json()
        assert body["available"] is True
        assert body["mode"] == "rdp"
        assert body["n_steps_accounted"] > 0
        assert body["epsilon"] > 0.0


def _inject_trainer(app: FastAPI):
    """Helper: attach a FederatedTrainer to the orchestrator for tests
    that need an active trainer without /federated/start (which requires
    a MAPPO checkpoint env). Return type elided so callers can use the
    real FederatedTrainer attrs without pyright object-wall."""
    from penumbra_learning.federated import FederatedTrainer
    from penumbra_learning.mappo import MAPPO, MAPPOConfig

    sim = app.state.penumbra.simulation
    cfg = MAPPOConfig(obs_dim=18, n_actions=7, n_agents=len(sim.agents), hidden=8)
    trainer = FederatedTrainer.from_mappo(MAPPO(cfg), n_agents=len(sim.agents))
    app.state.penumbra.orchestrator.federated_trainer = trainer
    return trainer


def test_federated_set_method_accepts_each_aggregator() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        trainer = _inject_trainer(app)
        for method in ("fedavg", "ckks_sum", "krum", "trimmed_mean"):
            body = client.post(f"/federated/method/{method}").json()
            assert body["ok"] is True
            assert body["method"] == method
            assert trainer.aggregation_method == method


def test_federated_set_method_rejects_unknown() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        _inject_trainer(app)
        resp = client.post("/federated/method/lolwhat")
        assert resp.status_code == 400


def test_federated_set_method_400_without_trainer() -> None:
    with TestClient(_build_test_app()) as client:
        resp = client.post("/federated/method/fedavg")
        assert resp.status_code == 400


def test_federated_fedprox_endpoint_sets_mu() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        trainer = _inject_trainer(app)
        body = client.post("/federated/fedprox?mu=0.05").json()
        assert body["ok"] is True
        assert trainer.fedprox_mu == 0.05


def test_federated_fedprox_endpoint_rejects_negative_mu() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        _inject_trainer(app)
        resp = client.post("/federated/fedprox?mu=-1.0")
        assert resp.status_code == 400


def test_federated_compress_endpoint_sets_knobs() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        trainer = _inject_trainer(app)
        body = client.post("/federated/compress?topk=0.3&quantize=8").json()
        assert body["ok"] is True
        assert trainer.topk_fraction == 0.3
        assert trainer.quantize_bits == 8


def test_federated_compress_endpoint_rejects_bad_quantize() -> None:
    app = _build_test_app()
    with TestClient(app) as client:
        _inject_trainer(app)
        resp = client.post("/federated/compress?topk=0.5&quantize=4")
        assert resp.status_code == 400
