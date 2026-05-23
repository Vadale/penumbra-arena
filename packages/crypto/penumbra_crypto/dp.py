"""Differential privacy with a privacy-budget accountant.

Concept taught: differential privacy gives a *quantitative* answer to
"how much information about any individual record can the released
statistic leak?". The Laplace mechanism adds noise scaled by
`sensitivity / ε`, where ε bounds the log-ratio of release probabilities
under any adjacent-dataset change.

The accountant is the load-bearing piece: every release deducts from
a total ε / δ budget; once exhausted, the system refuses further
releases rather than silently leaking. This is the practitioner
discipline that prevents "DP theatre" — DP without an accountant is
just noise.

In Penumbra we use DP to release aggregate statistics about agents
(mean position by region, count of agents in a goal area, variance of
trajectory lengths) without revealing any single agent's exact state.

References
----------
- Dwork & Roth. "The algorithmic foundations of differential privacy"
  (2014). The textbook; Theorem 3.16 covers composition.
- diffprivlib: https://github.com/IBM/differential-privacy-library
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


def secure_rng() -> np.random.Generator:
    """Return a `np.random.Generator` seeded from the OS CSPRNG.

    NumPy's PCG64 algorithm is statistically excellent but not
    cryptographically secure on its own — given a few outputs an
    adversary can reconstruct its state. Seeding it from
    `secrets.token_bytes` removes the *predictability* that an
    adversary needs to subtract Laplace noise from a DP release.
    For *adversarial* DP guarantees, every release should draw from
    a generator seeded this way (or from a different CSPRNG-backed
    bitgen). This helper is the canonical way to do so.
    """
    seed = int.from_bytes(secrets.token_bytes(8), "big")
    return np.random.default_rng(seed)


@dataclass(slots=True)
class PrivacyBudget:
    """Total (ε, δ)-DP budget across the run.

    Basic composition is used (sequential composition theorem). For each
    release we accumulate ε and δ. When `epsilon_spent >= epsilon` or
    `delta_spent >= delta`, the accountant raises before noising.
    """

    epsilon: float
    delta: float = 0.0
    epsilon_spent: float = 0.0
    delta_spent: float = 0.0

    def deduct(self, epsilon: float, delta: float = 0.0) -> None:
        if epsilon < 0 or delta < 0:
            raise ValueError("epsilon/delta deductions must be non-negative")
        if self.epsilon_spent + epsilon > self.epsilon + 1e-12:
            raise BudgetExceededError(
                f"ε budget exhausted: {self.epsilon_spent} + {epsilon} > {self.epsilon}"
            )
        if self.delta_spent + delta > self.delta + 1e-12:
            raise BudgetExceededError(
                f"δ budget exhausted: {self.delta_spent} + {delta} > {self.delta}"
            )
        self.epsilon_spent += epsilon
        self.delta_spent += delta

    @property
    def remaining_epsilon(self) -> float:
        return max(self.epsilon - self.epsilon_spent, 0.0)


class DPMechanism:
    """Laplace-mechanism wrapper that *requires* a budget accountant.

    The mechanism never noises without first deducting from the budget;
    if the deduction would overdraw, we raise *before* drawing noise so
    the caller can't pretend the release was tentative.

    The default `rng` is `secure_rng()` — a `np.random.Generator` seeded
    from `secrets.token_bytes`. PCG64 is not cryptographically secure
    standalone, but a CSPRNG-derived seed removes the predictability an
    adversary needs to subtract the Laplace noise from a release. For
    full adversarial DP, callers can pass any CSPRNG-backed Generator.
    Tests that need reproducibility should pass an explicit seeded
    Generator.
    """

    def __init__(self, budget: PrivacyBudget, rng: np.random.Generator | None = None) -> None:
        self._budget = budget
        self._rng = rng if rng is not None else secure_rng()

    @property
    def budget(self) -> PrivacyBudget:
        return self._budget

    def laplace(self, value: float, *, sensitivity: float, epsilon: float) -> float:
        """Release a noisy `value` with ε-DP.

        `sensitivity` is the L1 sensitivity of the underlying query
        (max change in `value` under a single-record adjacency).
        """
        if sensitivity <= 0:
            raise ValueError("sensitivity must be > 0")
        if epsilon <= 0:
            raise ValueError("epsilon must be > 0")
        self._budget.deduct(epsilon)
        scale = sensitivity / epsilon
        return float(value + self._rng.laplace(loc=0.0, scale=scale))

    def laplace_vector(
        self,
        values: NDArray[np.float64],
        *,
        sensitivity: float,
        epsilon: float,
    ) -> NDArray[np.float64]:
        """Per-coordinate Laplace noise. ε is the *total* budget for the vector.

        We add Laplace(sensitivity/ε) to each coordinate; by basic
        composition the vector release is ε-DP if `sensitivity` bounds
        the L∞ change across coordinates under adjacency.
        """
        if sensitivity <= 0 or epsilon <= 0:
            raise ValueError("sensitivity and epsilon must be > 0")
        self._budget.deduct(epsilon)
        scale = sensitivity / epsilon
        noise = self._rng.laplace(loc=0.0, scale=scale, size=values.shape)
        return values + noise


def dp_mean(
    samples: NDArray[np.float64],
    *,
    sensitivity: float,
    epsilon: float,
    mechanism: DPMechanism,
) -> float:
    """Differentially private mean.

    `sensitivity` is the sensitivity of the mean: usually
    `(upper - lower) / n` if values are clipped to `[lower, upper]`.
    """
    return mechanism.laplace(float(np.mean(samples)), sensitivity=sensitivity, epsilon=epsilon)


def dp_count(
    boolean_mask: NDArray[np.bool_],
    *,
    epsilon: float,
    mechanism: DPMechanism,
) -> float:
    """Differentially private count of `True` entries.

    Sensitivity = 1 by definition (one record change flips at most one
    boolean and so changes the count by at most 1).
    """
    return mechanism.laplace(float(np.sum(boolean_mask)), sensitivity=1.0, epsilon=epsilon)


def dp_histogram(
    counts: NDArray[np.float64],
    *,
    epsilon: float,
    mechanism: DPMechanism,
) -> NDArray[np.float64]:
    """Per-bin Laplace-noised histogram, ε-DP under L1 sensitivity = 1.

    Sensitivity reasoning: a single record changes one bin's count by ±1
    and so changes the L∞ of the histogram by at most 1.
    """
    return mechanism.laplace_vector(counts, sensitivity=1.0, epsilon=epsilon)


class BudgetExceededError(RuntimeError):
    """Raised when a release would push the privacy budget past its cap."""
