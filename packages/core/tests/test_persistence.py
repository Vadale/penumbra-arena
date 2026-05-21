"""Round-trip tests for the simulation snapshot."""

from __future__ import annotations

import tempfile
from pathlib import Path

from penumbra_core.persistence import load_simulation, save_simulation
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig


def test_save_restore_roundtrip_preserves_positions_and_tick() -> None:
    sim = Simulation.build(SimulationConfig(n_agents=8), bootstrap(seed=42))
    for _ in range(15):
        sim.tick()
    expected_tick = sim.tick_counter
    expected_positions = [a.position for a in sim.agents]
    expected_arena_tick = sim.arena.tick

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "sim.pkl"
        save_simulation(sim, path)
        restored = load_simulation(path)

    assert restored.tick_counter == expected_tick
    assert [a.position for a in restored.agents] == expected_positions
    assert restored.arena.tick == expected_arena_tick
    assert restored.config.n_agents == 8
    assert restored.seeded.master == 42


def test_restored_simulation_can_keep_ticking() -> None:
    sim = Simulation.build(SimulationConfig(n_agents=5), bootstrap(seed=7))
    for _ in range(5):
        sim.tick()

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "sim.pkl"
        save_simulation(sim, path)
        restored = load_simulation(path)

    starting_tick = restored.tick_counter
    for _ in range(3):
        restored.tick()
    assert restored.tick_counter == starting_tick + 3


def test_load_simulation_missing_file_raises() -> None:
    import pytest

    with tempfile.TemporaryDirectory() as tmpdir, pytest.raises(FileNotFoundError):
        load_simulation(Path(tmpdir) / "does-not-exist.pkl")
