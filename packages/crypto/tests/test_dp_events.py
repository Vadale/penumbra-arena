"""Phase 6a Tier 3 — DP-mechanism signalling tests.

Concept taught: a DP accountant doesn't just gate releases — it can
ALSO notify upstream consumers when the privacy budget is nearly or
fully spent. These tests pin the signalling contract used by the
cross-pillar event bus (warning at <5% remaining, exhausted at 0,
each fired exactly once, and reset re-arms both).
"""

from __future__ import annotations

import numpy as np
import pytest
from penumbra_crypto.dp import (
    BudgetExceededError,
    DPMechanism,
    PrivacyBudget,
)


def _rng() -> np.random.Generator:
    return np.random.default_rng(seed=42)


def test_warning_fires_exactly_once_at_threshold() -> None:
    """Crossing the 5% threshold emits one warning; further drains stay silent."""
    signals: list[tuple[str, dict[str, float]]] = []
    budget = PrivacyBudget(epsilon=1.0)
    mech = DPMechanism(budget, rng=_rng(), on_signal=lambda k, p: signals.append((k, p)))
    # Drain to 90% spent → remaining 10% → no signal yet (above 5%).
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.9)
    assert [k for k, _ in signals] == []
    # Drain another 6% → remaining 4% (<5%) → ONE warning.
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.06)
    assert [k for k, _ in signals] == ["dp.budget.warning"]
    # Drain another tiny slice → still below 5% but already warned → silent.
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.01)
    assert [k for k, _ in signals] == ["dp.budget.warning"]


def test_warning_payload_carries_remaining_and_total() -> None:
    signals: list[tuple[str, dict[str, float]]] = []
    budget = PrivacyBudget(epsilon=2.0)
    mech = DPMechanism(budget, rng=_rng(), on_signal=lambda k, p: signals.append((k, p)))
    mech.laplace(0.0, sensitivity=1.0, epsilon=1.95)
    assert len(signals) == 1
    kind, payload = signals[0]
    assert kind == "dp.budget.warning"
    assert payload["total"] == pytest.approx(2.0)
    assert payload["remaining"] == pytest.approx(0.05, abs=1e-9)


def test_exhausted_fires_when_remaining_reaches_zero() -> None:
    signals: list[str] = []
    budget = PrivacyBudget(epsilon=1.0)
    mech = DPMechanism(budget, rng=_rng(), on_signal=lambda k, _p: signals.append(k))
    # One single drain to 100% spent.
    mech.laplace(0.0, sensitivity=1.0, epsilon=1.0)
    # Warning AND exhausted both qualify; the implementation prefers
    # exhausted (more severe) so only exhausted fires.
    assert signals == ["dp.budget.exhausted"]


def test_exhausted_fires_at_most_once_even_when_overdraft_raises() -> None:
    signals: list[str] = []
    budget = PrivacyBudget(epsilon=1.0)
    mech = DPMechanism(budget, rng=_rng(), on_signal=lambda k, _p: signals.append(k))
    mech.laplace(0.0, sensitivity=1.0, epsilon=1.0)
    assert signals == ["dp.budget.exhausted"]
    # Subsequent overdraft attempts must not re-fire exhausted.
    with pytest.raises(BudgetExceededError):
        mech.laplace(0.0, sensitivity=1.0, epsilon=0.1)
    assert signals == ["dp.budget.exhausted"]


def test_warning_then_exhausted_separate_signals() -> None:
    signals: list[str] = []
    budget = PrivacyBudget(epsilon=1.0)
    mech = DPMechanism(budget, rng=_rng(), on_signal=lambda k, _p: signals.append(k))
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.96)  # warning
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.04)  # exhausted
    assert signals == ["dp.budget.warning", "dp.budget.exhausted"]


def test_reset_clears_warned_and_exhausted_flags() -> None:
    """After `reset_budget_flags()` the next drain past 5% re-fires warning."""
    signals: list[str] = []
    budget = PrivacyBudget(epsilon=1.0)
    mech = DPMechanism(budget, rng=_rng(), on_signal=lambda k, _p: signals.append(k))
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.96)
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.04)
    assert signals == ["dp.budget.warning", "dp.budget.exhausted"]
    mech.reset_budget_flags()
    assert budget.epsilon_spent == 0.0
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.96)
    assert signals[-1] == "dp.budget.warning"
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.04)
    assert signals[-1] == "dp.budget.exhausted"


def test_laplace_vector_also_signals() -> None:
    signals: list[str] = []
    budget = PrivacyBudget(epsilon=1.0)
    mech = DPMechanism(budget, rng=_rng(), on_signal=lambda k, _p: signals.append(k))
    mech.laplace_vector(np.array([1.0, 2.0]), sensitivity=1.0, epsilon=0.96)
    mech.laplace_vector(np.array([1.0, 2.0]), sensitivity=1.0, epsilon=0.04)
    assert signals == ["dp.budget.warning", "dp.budget.exhausted"]


def test_no_signal_when_handler_not_installed() -> None:
    """Bare DPMechanism without on_signal must not crash on threshold crossings."""
    budget = PrivacyBudget(epsilon=1.0)
    mech = DPMechanism(budget, rng=_rng())
    # No exception expected; budget should debit normally.
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.96)
    mech.laplace(0.0, sensitivity=1.0, epsilon=0.04)
    assert budget.epsilon_spent == pytest.approx(1.0, abs=1e-9)


def test_privacy_budget_reset_zeroes_spent() -> None:
    budget = PrivacyBudget(epsilon=1.0, delta=0.2)
    budget.deduct(0.5, delta=0.1)
    budget.reset()
    assert budget.epsilon_spent == 0.0
    assert budget.delta_spent == 0.0
