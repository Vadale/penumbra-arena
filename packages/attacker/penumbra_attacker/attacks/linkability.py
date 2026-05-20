"""Linkability: de-anonymising an agent from movement patterns.

How the attack works
--------------------
Even if agent IDs are randomised every match, if their *trajectories*
across matches are correlated, an observer can link two trajectories
to the same agent. The classic example is "the agent who always
visits node 17 first" — across N matches, that habit is a fingerprint.

We measure linkability by training a tiny nearest-neighbour matcher
on per-match trajectory signatures (mean position, variance, top-3
visit frequencies) and asking: given an unseen match's trajectory,
how often can the matcher correctly identify which agent it was?

Why Penumbra would resist (if the defence were enabled)
-------------------------------------------------------
A "shuffling" defence rotates agent identities + adds a small amount
of trajectory noise (Laplace on aggregate features) every match.
With noise calibrated to the linker's sensitivity, the matcher's
accuracy drops to random (1/N).

Try it
------
>>> from penumbra_attacker.attacks import linkability
>>> result = linkability.demo(n_agents=5, n_matches=20)
>>> result.naive_accuracy > 0.5   # the attack works
True
>>> result.with_noise_accuracy < 0.5  # the defence drops it
True
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class LinkabilityResult:
    n_agents: int
    n_matches: int
    naive_accuracy: float
    with_noise_accuracy: float


def demo(*, n_agents: int = 5, n_matches: int = 20, seed: int = 42) -> LinkabilityResult:
    """Simulate trajectory fingerprints with and without DP-style noise."""
    rng = np.random.default_rng(seed=seed)

    # Each agent has a *stable* preference vector (the fingerprint).
    preferences = rng.standard_normal((n_agents, 5))

    # Per match, each agent's "trajectory signature" is preference + small noise.
    train_signatures = preferences + 0.3 * rng.standard_normal((n_agents, 5))
    test_signatures_clean = preferences + 0.3 * rng.standard_normal((n_agents, 5))
    test_signatures_noisy = test_signatures_clean + 1.5 * rng.standard_normal((n_agents, 5))

    naive_correct = 0
    noisy_correct = 0
    for _ in range(n_matches):
        for true_id in range(n_agents):
            naive_correct += (
                _nearest_match(train_signatures, test_signatures_clean[true_id]) == true_id
            )
            noisy_correct += (
                _nearest_match(train_signatures, test_signatures_noisy[true_id]) == true_id
            )
            # Re-sample the test signature so the result isn't trivially deterministic.
            test_signatures_clean[true_id] = preferences[true_id] + 0.3 * rng.standard_normal(5)
            test_signatures_noisy[true_id] = test_signatures_clean[
                true_id
            ] + 1.5 * rng.standard_normal(5)

    total = n_agents * n_matches
    return LinkabilityResult(
        n_agents=n_agents,
        n_matches=n_matches,
        naive_accuracy=naive_correct / total,
        with_noise_accuracy=noisy_correct / total,
    )


def _nearest_match(database: NDArray[np.float64], query: NDArray[np.float64]) -> int:
    """1-NN match by Euclidean distance."""
    distances = np.linalg.norm(database - query, axis=1)
    return int(np.argmin(distances))
