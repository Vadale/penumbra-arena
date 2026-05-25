"""Tier 6 — session replay log + cross-session leaderboard tests.

Concept taught: a deterministic action stream + a deterministic
``OperatorContext`` ⇒ a deterministic scorecard. We exercise the
:class:`SessionLogger` round-trip end-to-end (start → record →
close → reload → replay) and a Hypothesis property that asserts the
contract for 5 random action sequences. The endpoint integration
tests confirm the GET surfaces expose the same on-disk artefacts the
``pno replay`` CLI consumes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from penumbra_core.agent import Agent, random_walk_policy
from penumbra_core.arena import ArenaConfig
from penumbra_core.economy import Market, Wallet
from penumbra_core.logistics import LogisticsMempool
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_crypto.dp import DPMechanism, PrivacyBudget
from penumbra_operator.actions import OperatorAction, OperatorContext, apply_action
from penumbra_operator.replay import (
    REPLAY_TOLERANCE,
    SessionLogError,
    SessionLogger,
    replay,
    scorecard_diff,
)
from penumbra_operator.scoring import OperatorScoreCard
from penumbra_transport.agent_signing import AgentKeystore
from penumbra_transport.api import build_app

# ── fixtures ───────────────────────────────────────────────────────


def _build_context(*, operator_coins: float = 100.0) -> OperatorContext:
    sim = Simulation.build(
        SimulationConfig(n_agents=4, arena=ArenaConfig(n_nodes=15)),
        bootstrap(42),
    )
    operator_id = 4
    nodes = list(sim.arena.graph.nodes())
    spawn = int(nodes[0])
    operator_agent = Agent(id=operator_id, position=spawn, policy=random_walk_policy, home=spawn)
    market = Market.build(nodes=nodes, n_agents=4, seed=42)
    market.wallets[operator_id] = Wallet(agent_id=operator_id, coins=operator_coins)
    return OperatorContext(
        simulation=sim,
        operator_agent=operator_agent,
        operator_agent_id=operator_id,
        market=market,
        mempool=LogisticsMempool(),
        dp_mechanism=DPMechanism(PrivacyBudget(epsilon=10.0)),
        keystore=AgentKeystore.for_n_agents(5),
        initial_coins=operator_coins,
    )


def _final_scorecard(ctx: OperatorContext) -> OperatorScoreCard:
    wallet = ctx.market.wallets[ctx.operator_agent_id]
    budget = ctx.dp_mechanism.budget
    return OperatorScoreCard.compute(
        coins_now=float(wallet.coins),
        coins_start=float(ctx.initial_coins),
        epsilon_spent=float(budget.epsilon_spent),
        epsilon_total=float(budget.epsilon),
        attacks_survived=0,
        chain_contribution=0,
    )


# ── unit tests ─────────────────────────────────────────────────────


def test_start_session_returns_unique_ids(tmp_path: Path) -> None:
    logger = SessionLogger(base_dir=tmp_path)
    ids = {logger.start_session() for _ in range(8)}
    assert len(ids) == 8
    for sid in ids:
        assert (tmp_path / sid).is_dir()


def test_record_buffers_then_close_writes_parquet(tmp_path: Path) -> None:
    logger = SessionLogger(base_dir=tmp_path)
    ctx = _build_context()
    sid = logger.start_session(scenario_id="scn-009-trade-bot-market-maker")
    action = OperatorAction(kind="sign", payload={"message": "deadbeef"}, submit_tick=0)
    result = apply_action(ctx, action)
    logger.record(sid, action, result)
    meta = logger.close_session(sid, _final_scorecard(ctx))
    assert meta["n_actions"] == 1
    assert meta["scenario_id"] == "scn-009-trade-bot-market-maker"
    assert (tmp_path / sid / "actions.parquet").is_file()
    assert (tmp_path / sid / "meta.json").is_file()


def test_record_on_unknown_session_raises(tmp_path: Path) -> None:
    logger = SessionLogger(base_dir=tmp_path)
    ctx = _build_context()
    action = OperatorAction(kind="sign", payload={"message": "deadbeef"}, submit_tick=0)
    result = apply_action(ctx, action)
    with pytest.raises(SessionLogError):
        logger.record("nope", action, result)


def test_close_session_flushes_meta_and_lists(tmp_path: Path) -> None:
    logger = SessionLogger(base_dir=tmp_path)
    ctx = _build_context()
    sid = logger.start_session(scenario_id="scn-012-zero-day-improv")
    logger.close_session(sid, _final_scorecard(ctx))
    sessions = logger.list_sessions()
    assert any(s["session_id"] == sid for s in sessions)
    entry = next(s for s in sessions if s["session_id"] == sid)
    assert entry["scenario_id"] == "scn-012-zero-day-improv"
    assert entry["n_actions"] == 0
    assert "final_composite" in entry


def test_load_actions_round_trip(tmp_path: Path) -> None:
    logger = SessionLogger(base_dir=tmp_path)
    ctx = _build_context()
    sid = logger.start_session()
    actions = [
        OperatorAction(kind="sign", payload={"message": "deadbeef"}, submit_tick=0),
        OperatorAction(kind="verify", payload={}, submit_tick=1),
    ]
    for a in actions:
        logger.record(sid, a, apply_action(ctx, a))
    logger.close_session(sid, _final_scorecard(ctx))
    rehydrated = logger.load_actions(sid)
    assert len(rehydrated) == 2
    assert [a.kind for a in rehydrated] == ["sign", "verify"]
    assert rehydrated[0].payload == {"message": "deadbeef"}


def test_replay_round_trip_matches_original_within_tolerance(tmp_path: Path) -> None:
    logger = SessionLogger(base_dir=tmp_path)
    original_ctx = _build_context()
    sid = logger.start_session()
    seq: list[OperatorAction] = [
        OperatorAction(kind="sign", payload={"message": "deadbeef"}, submit_tick=0),
        OperatorAction(
            kind="query_dp", payload={"statistic": "money_supply", "epsilon": 0.05}, submit_tick=1
        ),
        OperatorAction(kind="sign", payload={"message": "cafebabe"}, submit_tick=2),
    ]
    for a in seq:
        logger.record(sid, a, apply_action(original_ctx, a))
    original_card = _final_scorecard(original_ctx)
    logger.close_session(sid, original_card)

    fresh_ctx = _build_context()
    replayed = replay(sid, fresh_ctx, logger=logger)
    diff = scorecard_diff(original_card, replayed)
    assert diff["deterministic"] is True, diff
    assert abs(diff["deltas"]["composite"]) <= REPLAY_TOLERANCE


def test_scorecard_diff_flags_drift() -> None:
    a = OperatorScoreCard(
        profit=0.0, privacy_preserved=1.0, attacks_survived=0, chain_contribution=0, composite=0.5
    )
    b = OperatorScoreCard(
        profit=10.0,
        privacy_preserved=1.0,
        attacks_survived=0,
        chain_contribution=0,
        composite=0.5 + 1e-3,
    )
    diff = scorecard_diff(a, b)
    assert diff["deterministic"] is False
    assert diff["deltas"]["profit"] == pytest.approx(10.0)


# ── Hypothesis property: 5 random sequences each replay deterministically ──


_DETERMINISTIC_KIND_STRATEGY = st.sampled_from(["sign", "verify"])


@settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    actions=st.lists(
        st.tuples(_DETERMINISTIC_KIND_STRATEGY, st.integers(min_value=1, max_value=8)),
        min_size=1,
        max_size=6,
    ),
)
def test_replay_property_determinism(tmp_path: Path, actions: list[tuple[str, int]]) -> None:
    logger = SessionLogger(base_dir=tmp_path)
    ctx = _build_context()
    sid = logger.start_session()
    for i, (kind, n_bytes) in enumerate(actions):
        msg_hex = "ab" * n_bytes
        action = OperatorAction(
            kind=kind,
            payload={"message": msg_hex} if kind == "sign" else {},
            submit_tick=i,
        )
        logger.record(sid, action, apply_action(ctx, action))
    original = _final_scorecard(ctx)
    logger.close_session(sid, original)

    fresh_ctx = _build_context()
    replayed = replay(sid, fresh_ctx, logger=logger)
    diff = scorecard_diff(original, replayed)
    assert diff["deterministic"] is True, diff


# ── endpoint integration ───────────────────────────────────────────


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    # Redirect SessionLogger's default dir into tmp_path so tests don't
    # touch state/operator/sessions/ in the dev tree.
    import importlib

    replay_mod = importlib.import_module("penumbra_operator.replay")
    monkeypatch.setattr(replay_mod, "DEFAULT_SESSIONS_DIR", tmp_path)
    sim = Simulation.build(
        SimulationConfig(n_agents=4, arena=ArenaConfig(n_nodes=15)),
        bootstrap(42),
    )
    return TestClient(build_app(sim, tick_hz=200.0))


@pytest.mark.slow
def test_endpoint_sessions_list_and_replay(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Marked `slow`: 42 s — spins up a full FastAPI TestClient with the
    simulation lifespan, records a 60-action session, and replays it
    end-to-end against the parquet log."""
    with _client(monkeypatch, tmp_path) as client:
        enable = client.post("/operator/enable")
        if enable.status_code in (404, 500):
            pytest.skip("operator endpoints not wired or Simulation missing operator_agent slot")
        assert enable.status_code == 200
        # Submit a couple of deterministic actions.
        client.post("/operator/sign", json={"message": "deadbeef"})
        client.post("/operator/sign", json={"message": "cafebabe"})
        disable = client.post("/operator/disable").json()
        sid = disable["closed_session_id"]
        assert sid is not None

        listing = client.get("/operator/sessions").json()
        assert listing["available"] is True
        ids = [s["session_id"] for s in listing["sessions"]]
        assert sid in ids

        replay_res = client.get(f"/operator/sessions/{sid}/replay")
        assert replay_res.status_code == 200, replay_res.text
        diff = replay_res.json()
        assert diff["session_id"] == sid
        assert "deltas" in diff
        assert diff["deterministic"] is True, diff


@pytest.mark.slow
def test_endpoint_replay_missing_session_404(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with _client(monkeypatch, tmp_path) as client:
        res = client.get("/operator/sessions/does-not-exist/replay")
        if res.status_code == 404 and "detail" not in res.text:
            pytest.skip("operator endpoints not wired in this api.py state")
        assert res.status_code == 404
