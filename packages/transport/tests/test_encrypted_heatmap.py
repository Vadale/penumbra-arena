"""End-to-end test for the runtime encrypted heatmap."""

from __future__ import annotations

import numpy as np
import pytest
from penumbra_core.arena import ArenaConfig
from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_crypto.ckks import TenSEALBackend
from penumbra_transport.encrypted_heatmap import EncryptedHeatmap


@pytest.fixture(scope="module")
def backend() -> TenSEALBackend:
    return TenSEALBackend()


def _build_sim() -> Simulation:
    return Simulation.build(
        SimulationConfig(n_agents=10, arena=ArenaConfig(n_nodes=15)),
        bootstrap(42),
    )


def test_heatmap_sum_matches_agent_count(backend: TenSEALBackend) -> None:
    """The decrypted aggregate should sum to (approximately) the number of agents."""
    sim = _build_sim()
    heatmap = EncryptedHeatmap.for_simulation(backend, sim)
    sample = heatmap.compute(sim)
    assert sample.density.shape == (15,)
    # CKKS approximation noise — allow a small slack.
    assert abs(sample.decrypted_total - len(sim.agents)) < 1e-2


def test_heatmap_matches_plaintext_bincount(backend: TenSEALBackend) -> None:
    """Decrypted aggregate must equal a plaintext bincount of agent positions."""
    sim = _build_sim()
    heatmap = EncryptedHeatmap.for_simulation(backend, sim)
    sample = heatmap.compute(sim)

    positions = np.array([a.position for a in sim.agents])
    expected = np.bincount(positions, minlength=15).astype(np.float64)
    np.testing.assert_allclose(sample.density, expected, atol=1e-2)


def test_heatmap_latest_cached(backend: TenSEALBackend) -> None:
    sim = _build_sim()
    heatmap = EncryptedHeatmap.for_simulation(backend, sim)
    assert heatmap.latest is None
    sample = heatmap.compute(sim)
    assert heatmap.latest is sample
