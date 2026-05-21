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


def test_dp_noised_release_consumes_budget(backend: TenSEALBackend) -> None:
    """With a DP mechanism attached, each compute() spends epsilon."""
    from penumbra_crypto.dp import DPMechanism, PrivacyBudget

    sim = _build_sim()
    budget = PrivacyBudget(epsilon=1.0)
    mechanism = DPMechanism(budget)
    heatmap = EncryptedHeatmap.for_simulation(
        backend, sim, dp_mechanism=mechanism, dp_epsilon_per_release=0.1
    )
    sample = heatmap.compute(sim)
    assert sample.noise_applied
    assert abs(sample.epsilon_spent_total - 0.1) < 1e-9
    # And after the second release, ε spent should be 0.2.
    sample2 = heatmap.compute(sim)
    assert abs(sample2.epsilon_spent_total - 0.2) < 1e-9


def test_dp_falls_back_to_clean_when_budget_exhausted(backend: TenSEALBackend) -> None:
    """Past the ε budget the mechanism logs a warning and releases un-noised."""
    from penumbra_crypto.dp import DPMechanism, PrivacyBudget

    sim = _build_sim()
    budget = PrivacyBudget(epsilon=0.2)
    mechanism = DPMechanism(budget)
    heatmap = EncryptedHeatmap.for_simulation(
        backend, sim, dp_mechanism=mechanism, dp_epsilon_per_release=0.15
    )
    first = heatmap.compute(sim)
    assert first.noise_applied
    second = heatmap.compute(sim)
    # Second release would overdraw — falls back to clean.
    assert not second.noise_applied
    # The clean sum equals the agent count exactly.
    assert abs(second.decrypted_total - len(sim.agents)) < 1e-2
