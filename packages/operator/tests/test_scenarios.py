"""Tier 5 scenario tests — schema, victory/failure scripting, abandon.

Concept taught: a scenario is a YAML contract between author and
runner. We verify each of the 12 starter YAMLs parses + validates,
then drive the easiest one (scn-009-trade-bot-market-maker) through
both a winning and a losing sequence so the runner's status reporter
is exercised in both polarities.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from penumbra_core.arena import ArenaConfig
from penumbra_core.economy import Market, Wallet
from penumbra_core.logistics import LogisticsMempool
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_crypto.dp import DPMechanism, PrivacyBudget
from penumbra_operator.actions import OperatorContext
from penumbra_operator.scenarios import (
    SCENARIOS_DIR,
    Scenario,
    ScenarioError,
    ScenarioRunner,
    load_scenarios,
)
from penumbra_transport.agent_signing import AgentKeystore

EXPECTED_IDS: tuple[str, ...] = (
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
)


# ── fixtures ───────────────────────────────────────────────────────


def _build_context(*, operator_coins: float = 100.0) -> OperatorContext:
    sim = Simulation.build(
        SimulationConfig(n_agents=4, arena=ArenaConfig(n_nodes=15)),
        bootstrap(42),
    )
    from penumbra_core.agent import Agent, random_walk_policy

    operator_id = 4
    nodes = list(sim.arena.graph.nodes())
    spawn = int(nodes[0])
    operator_agent = Agent(id=operator_id, position=spawn, policy=random_walk_policy, home=spawn)
    sim.operator_agent = operator_agent
    market = Market.build(nodes=nodes, n_agents=4, seed=42)
    market.wallets[operator_id] = Wallet(agent_id=operator_id, coins=operator_coins)
    mempool = LogisticsMempool()
    dp = DPMechanism(PrivacyBudget(epsilon=10.0))
    keystore = AgentKeystore.for_n_agents(5)
    return OperatorContext(
        simulation=sim,
        operator_agent=operator_agent,
        operator_agent_id=operator_id,
        market=market,
        mempool=mempool,
        dp_mechanism=dp,
        keystore=keystore,
        initial_coins=operator_coins,
    )


@pytest.fixture(scope="module")
def loaded_scenarios() -> list[Scenario]:
    return load_scenarios(SCENARIOS_DIR)


@pytest.fixture(scope="module")
def scenarios_by_id(loaded_scenarios: list[Scenario]) -> dict[str, Scenario]:
    return {s.id: s for s in loaded_scenarios}


# ── 12 schema tests (parametrised) ─────────────────────────────────


@pytest.mark.parametrize("scenario_id", EXPECTED_IDS)
def test_scenario_yaml_parses_and_validates(
    scenarios_by_id: dict[str, Scenario], scenario_id: str
) -> None:
    scn = scenarios_by_id.get(scenario_id)
    assert scn is not None, f"{scenario_id} missing from loaded scenarios"
    assert scn.title
    assert scn.difficulty in {"easy", "medium", "hard", "open"}
    # Weights are floats and sum to (approximately) 1.0.
    if scn.scoring.weights:
        total = sum(scn.scoring.weights.values())
        assert abs(total - 1.0) < 1e-6, (
            f"{scenario_id} scoring weights should sum to 1.0, got {total}"
        )
    # Either both victory + failure are empty (sandbox) or both are non-empty.
    assert (len(scn.victory) == 0) == (len(scn.failure) == 0) or scn.difficulty == "open"


def test_all_twelve_scenarios_present(scenarios_by_id: dict[str, Scenario]) -> None:
    assert set(scenarios_by_id.keys()) == set(EXPECTED_IDS)


def test_loader_rejects_missing_dir() -> None:
    with pytest.raises(ScenarioError):
        load_scenarios(Path("/nonexistent/path/scenarios"))


def test_loader_rejects_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: only-id\n", encoding="utf-8")
    with pytest.raises(ScenarioError):
        load_scenarios(tmp_path)


# ── runner lifecycle ───────────────────────────────────────────────


def test_runner_unknown_scenario_raises() -> None:
    runner = ScenarioRunner.from_directory()
    ctx = _build_context()
    with pytest.raises(ScenarioError):
        runner.start("scn-does-not-exist", ctx)
    with pytest.raises(ScenarioError):
        runner.check_status("scn-does-not-exist", ctx)


def test_runner_start_returns_opening_event_and_records_session() -> None:
    runner = ScenarioRunner.from_directory()
    ctx = _build_context()
    info = runner.start("scn-009-trade-bot-market-maker", ctx)
    assert info["scenario_id"] == "scn-009-trade-bot-market-maker"
    assert info["opening_event"]["kind"] == "operator.scenario.start"
    assert runner.session("scn-009-trade-bot-market-maker") is not None


def test_runner_abandon_removes_session_idempotent() -> None:
    runner = ScenarioRunner.from_directory()
    ctx = _build_context()
    runner.start("scn-009-trade-bot-market-maker", ctx)
    first = runner.abandon("scn-009-trade-bot-market-maker")
    assert first["abandoned"] is True
    second = runner.abandon("scn-009-trade-bot-market-maker")
    assert second["abandoned"] is False
    assert runner.session("scn-009-trade-bot-market-maker") is None


# ── scripted winning + losing sequences for scn-009 ────────────────


def test_scn009_winning_sequence_reaches_victory() -> None:
    """Win = profit > 50 AND >= 3 fulfilled carrier orders."""
    runner = ScenarioRunner.from_directory()
    ctx = _build_context(operator_coins=100.0)
    runner.start("scn-009-trade-bot-market-maker", ctx)

    # Pump the wallet beyond +50 and fulfil three carrier orders.
    wallet = ctx.market.wallets[ctx.operator_agent_id]
    wallet.coins = 200.0  # operator now has +100 profit

    city = next(iter(ctx.market.markets))
    for _ in range(3):
        order = ctx.mempool.place(
            city=int(city),
            product=0,
            quantity=1,
            tick=int(ctx.simulation.tick_counter),
            reward=1.0,
            assigned_to=ctx.operator_agent_id,
        )
        ctx.mempool.fulfil(order.id, ctx.operator_agent_id, int(ctx.simulation.tick_counter))

    status = runner.check_status("scn-009-trade-bot-market-maker", ctx)
    assert status["victory_met"] is True, status
    assert status["failure_met"] is False


def test_scn009_losing_sequence_hits_failure() -> None:
    """Fail = coins < 0 OR elapsed_ticks > 2500."""
    runner = ScenarioRunner.from_directory()
    ctx = _build_context(operator_coins=100.0)
    runner.start("scn-009-trade-bot-market-maker", ctx)

    # Drain the wallet below zero so the failure clause trips.
    ctx.market.wallets[ctx.operator_agent_id].coins = -5.0

    status = runner.check_status("scn-009-trade-bot-market-maker", ctx)
    assert status["failure_met"] is True
    assert status["victory_met"] is False


def test_status_for_inactive_scenario_is_flat() -> None:
    runner = ScenarioRunner.from_directory()
    ctx = _build_context()
    status = runner.check_status("scn-001-bullwhip-defender", ctx)
    assert status["active"] is False
    assert status["victory_met"] is False
    assert status["failure_met"] is False
