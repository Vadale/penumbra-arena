"""Dinur-Nissim: reconstructing private data from many DP releases.

Concept taught: differential privacy protects against *one* clever
query, not against *many* random ones — so a privacy guarantee
without a *budget accountant* is not a privacy guarantee. The fix is
ε-tracking that hard-caps total releases, regardless of how the
queries arrive.

How the attack works
--------------------
DP is robust against *one* clever query. It is NOT robust against
*many* random queries with noise calibrated to 1/ε. Dinur & Nissim
(2003) showed that an adversary who can submit n^Ω(1) random linear
queries against a sensitive bit-vector of length n can reconstruct
the entire vector with high probability — as long as the per-query
noise is asymptotically smaller than √n.

The intuition: each query is a linear projection plus noise; collect
enough queries and solve a least-squares system. With small enough
noise the LS solution rounds back to the true bit vector.

Why Penumbra resists it (when the accountant is used)
-----------------------------------------------------
The DP accountant in `penumbra_crypto.dp` *caps* the total ε that
can ever be spent. Once exhausted, the system refuses further
releases. Dinur-Nissim needs many queries; with ε_total = 1.0 and
ε_per_query = 0.05, only 20 queries fit in the budget — far below
the polynomial Dinur-Nissim needs.

Try it
------
>>> from penumbra_attacker.attacks import dp_reconstruction
>>> r = dp_reconstruction.demo(n_bits=32, n_queries=200, noise_scale=0.1)
>>> r.recovered_bit_accuracy > 0.85
True
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class ReconstructionResult:
    n_bits: int
    n_queries: int
    noise_scale: float
    recovered_bit_accuracy: float


def demo(
    *,
    n_bits: int = 32,
    n_queries: int = 200,
    noise_scale: float = 0.1,
    seed: int = 42,
) -> ReconstructionResult:
    """Demonstrate Dinur-Nissim recovery against an unaccounted DP release."""
    rng = np.random.default_rng(seed=seed)

    # The secret: a uniform binary vector.
    secret = rng.integers(0, 2, size=n_bits)

    # Adversary submits random ±1 query vectors; the "DP" mechanism
    # answers each with a noisy inner product (Laplace noise).
    queries = rng.choice([-1, 1], size=(n_queries, n_bits))
    true_answers = queries @ secret
    noise = rng.laplace(loc=0.0, scale=noise_scale, size=n_queries)
    observed = true_answers + noise

    # Reconstruction: solve the (overdetermined) least-squares system.
    reconstructed, _, _, _ = np.linalg.lstsq(queries, observed, rcond=None)
    recovered_bits = (reconstructed >= 0.5).astype(int)
    accuracy = float(np.mean(recovered_bits == secret))

    return ReconstructionResult(
        n_bits=n_bits,
        n_queries=n_queries,
        noise_scale=noise_scale,
        recovered_bit_accuracy=accuracy,
    )


def reconstruct_from_log(
    queries: NDArray[np.int_], noisy_answers: NDArray[np.float64]
) -> NDArray[np.int_]:
    """Useful as a building block: reconstruct bits from a real query log.

    Caller supplies the (m × n) query matrix and the m noisy answers.
    Returns the recovered n-vector.
    """
    if queries.shape[0] != noisy_answers.shape[0]:
        raise ValueError("queries and noisy_answers must have matching first dim")
    reconstructed, _, _, _ = np.linalg.lstsq(queries, noisy_answers, rcond=None)
    return (reconstructed >= 0.5).astype(int)
