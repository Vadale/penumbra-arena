"""End-to-end tests for the simulation tick loop."""

from __future__ import annotations

import pytest
from penumbra_core.arena import ArenaConfig
from penumbra_core.match import MatchStatus
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import RunState, Simulation, SimulationConfig


@pytest.fixture
def sim() -> Simulation:
    return Simulation.build(
        SimulationConfig(n_agents=10, arena=ArenaConfig(n_nodes=20)),
        bootstrap(42),
    )


def test_tick_advances_counter(sim: Simulation) -> None:
    sim.tick()
    assert sim.tick_counter == 1


def test_pause_stops_tick(sim: Simulation) -> None:
    sim.pause()
    frame = sim.tick()
    assert frame is None
    assert sim.tick_counter == 0


def test_step_once_advances_even_when_paused(sim: Simulation) -> None:
    sim.pause()
    sim.step_once()
    assert sim.tick_counter == 1
    assert sim.state is RunState.PAUSED


def test_time_warp_advances_multiple_ticks() -> None:
    sim = Simulation.build(
        SimulationConfig(n_agents=10, arena=ArenaConfig(n_nodes=20), time_warp=5),
        bootstrap(42),
    )
    sim.tick()
    assert sim.tick_counter == 5


def test_match_eventually_ends() -> None:
    """Run long enough that at least one match transitions away from RUNNING."""
    sim = Simulation.build(
        SimulationConfig(
            n_agents=20,
            arena=ArenaConfig(n_nodes=15, n_goals=5),
            match_max_ticks=200,
        ),
        bootstrap(42),
    )
    for _ in range(2_000):
        sim.tick()
    assert sim.next_match_id > 1, "expected at least one match to have ended"


def test_reproducibility_across_runs() -> None:
    sim_a = Simulation.build(
        SimulationConfig(n_agents=8, arena=ArenaConfig(n_nodes=15)), bootstrap(123)
    )
    sim_b = Simulation.build(
        SimulationConfig(n_agents=8, arena=ArenaConfig(n_nodes=15)), bootstrap(123)
    )
    for _ in range(50):
        sim_a.tick()
        sim_b.tick()
    assert {a.id: a.position for a in sim_a.agents} == {a.id: a.position for a in sim_b.agents}


def test_match_end_callback_fires() -> None:
    sim = Simulation.build(
        SimulationConfig(
            n_agents=15,
            arena=ArenaConfig(n_nodes=10, n_goals=4),
            match_max_ticks=50,
        ),
        bootstrap(42),
    )
    calls: list[str] = []
    sim.on_match_end = lambda match, _arena, _agents: calls.append(match.status.value)

    for _ in range(500):
        sim.tick()

    assert calls, "callback should fire at least once"
    assert all(status in {MatchStatus.WON.value, MatchStatus.EXPIRED.value} for status in calls)


def test_agents_stay_on_graph(sim: Simulation) -> None:
    valid_nodes = set(sim.arena.graph.nodes())
    for _ in range(200):
        sim.tick()
    for agent in sim.agents:
        assert agent.position in valid_nodes
