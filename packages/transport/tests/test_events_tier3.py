"""End-to-end wiring for Phase 6a Tier 3 — DP-budget pressure.

Concept taught: a DP-mechanism budget warning / exhaustion travels
from the encrypted-heatmap path → orchestrator EventBus → pipeline
degraded-mode flag + federated-trainer DP gate, in a single tick.
"""

from __future__ import annotations

from penumbra_core.rng import bootstrap
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_transport.events import Event
from penumbra_transport.orchestrator import Orchestrator


def _build_orchestrator() -> Orchestrator:
    sim = Simulation.build(SimulationConfig(n_agents=4, match_max_ticks=50), bootstrap(seed=17))
    # Tiny ε budget so the test can drain it cheaply via direct laplace calls.
    return Orchestrator.build(sim, n_validators=2, dp_total_epsilon=1.0)


def test_dp_warning_event_halves_pipeline_cadences() -> None:
    orch = _build_orchestrator()
    before = {key: orch.pipeline.cadences[key] for key in ("garch", "bayesian", "topics")}
    orch.event_bus.emit(
        Event(kind="dp.budget.warning", tick=0, payload={"remaining": 0.04, "total": 1.0})
    )
    for key, base in before.items():
        assert orch.pipeline.cadences[key] == base * 2.0


def test_dp_exhausted_event_flips_pipeline_degraded() -> None:
    orch = _build_orchestrator()
    assert orch.pipeline._dp_degraded is False
    orch.event_bus.emit(Event(kind="dp.budget.exhausted", tick=0, payload={"total": 1.0}))
    assert orch.pipeline._dp_degraded is True
    assert orch.pipeline._dp_degradation_reason == "dp_budget_exhausted"


def test_dp_mechanism_signal_threads_through_bus() -> None:
    """Draining the live DP mechanism past 95% must drive the bus."""
    orch = _build_orchestrator()
    mech = orch.heatmap.dp_mechanism
    assert mech is not None
    # Drain to just under the warning threshold so the threshold-cross
    # happens on the next debit.
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.96)
    kinds = [e.kind for e in orch.event_bus.recent(limit=10)]
    assert "dp.budget.warning" in kinds
    # Pipeline cadences should be halved by the auto-wired handler.
    assert orch.pipeline.cadences["garch"] > 30.0  # base is 30.0
