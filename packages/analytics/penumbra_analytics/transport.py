"""Optimal transport between two distributions (Sinkhorn).

Concept taught: optimal transport answers "what's the cheapest way to
turn distribution P into distribution Q?". The cost is the
**Wasserstein distance**; the *plan* is the joint distribution that
achieves it. Sinkhorn's algorithm (Cuturi 2013) approximates the plan
in O(n²/ε) iterations by adding an entropic regulariser — fast enough
that we can do it every 5 seconds against the encrypted heatmap.

In Penumbra we Sinkhorn-flow consecutive heatmaps to visualise the
*movement field*: where mass is shifting on the grid between t-1 and
t. Even though agent positions are encrypted, their aggregate flow
isn't — and the flow is the most readable summary of group behaviour.

References
- Cuturi, "Sinkhorn distances: lightspeed computation of optimal
  transport" (NeurIPS 2013).
- Peyré & Cuturi, "Computational optimal transport" (2019).
- POT: https://pythonot.github.io/
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import ot
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class TransportPlan:
    """The Sinkhorn-regularised transport plan + the associated cost."""

    plan: NDArray[np.float64]  # shape (m, n)
    cost: float  # entropic-regularised Wasserstein-2 cost
    iters: int


def sinkhorn_plan(
    source: NDArray[np.float64],
    target: NDArray[np.float64],
    *,
    cost_matrix: NDArray[np.float64] | None = None,
    reg: float = 0.1,
    max_iter: int = 200,
) -> TransportPlan:
    """Compute the Sinkhorn plan between source and target probability vectors.

    Vectors are auto-normalised. If `cost_matrix` is not given we
    construct it as |i - j| (1-D ground distance) — appropriate for
    grid-aligned histograms.
    """
    if source.ndim != 1 or target.ndim != 1:
        raise ValueError("source and target must be 1-D")
    source_norm = source / source.sum() if source.sum() > 0 else source.copy()
    target_norm = target / target.sum() if target.sum() > 0 else target.copy()
    if cost_matrix is None:
        m, n = source.size, target.size
        cost_matrix = np.abs(
            np.arange(m, dtype=np.float64).reshape(-1, 1)
            - np.arange(n, dtype=np.float64).reshape(1, -1)
        )
    plan_raw = ot.sinkhorn(source_norm, target_norm, cost_matrix, reg, numItermax=max_iter)
    plan = np.asarray(plan_raw, dtype=np.float64)
    cost = float(np.sum(plan * cost_matrix))
    return TransportPlan(plan=plan, cost=cost, iters=max_iter)


def wasserstein_1d(source: NDArray[np.float64], target: NDArray[np.float64]) -> float:
    """Exact 1-D Wasserstein-1 distance via the CDF formula.

    For 1-D distributions this avoids the Sinkhorn iteration entirely
    and is provably optimal. Useful when comparing two arena heatmaps
    at the same grid layout.
    """
    if source.shape != target.shape:
        raise ValueError("1-D Wasserstein requires aligned histograms")
    source_norm = source / source.sum() if source.sum() > 0 else source.copy()
    target_norm = target / target.sum() if target.sum() > 0 else target.copy()
    cdf_source = np.cumsum(source_norm)
    cdf_target = np.cumsum(target_norm)
    return float(np.sum(np.abs(cdf_source - cdf_target)))
