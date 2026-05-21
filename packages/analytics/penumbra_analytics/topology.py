"""Topological data analysis via persistent homology (ripser).

Concept taught: shape, not just position. Persistent homology counts
topological features (connected components, loops, voids) that survive
across many distance scales — those that *persist* are real structure,
not noise. The output is a **persistence diagram**: each (birth,
death) pair is a feature that appeared at scale `birth` and merged or
filled in at scale `death`.

In Penumbra we run persistent homology on the coalition-graph
filtration: as the encrypted-proximity threshold rises, edges accrue,
and coalitions form (H_0 dies) or close into loops (H_1 is born).

References
- Edelsbrunner, Harer, "Computational Topology" (2010).
- Bauer, "Ripser: efficient computation of Vietoris-Rips persistence
  barcodes" (J. Appl. Comput. Topol. 2021).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from ripser import ripser


@dataclass(frozen=True, slots=True)
class PersistenceDiagram:
    """Per-dimension list of (birth, death) intervals.

    `h0`: connected-component births and deaths (the longest interval
    is the global component and lives to infinity).
    `h1`: loop births and deaths. A non-trivial bar in H_1 means the
    coalition graph has a hole at that scale.
    """

    h0: NDArray[np.float64]  # shape (k, 2)
    h1: NDArray[np.float64]


def persistence_from_points(
    points: NDArray[np.float64],
    *,
    max_dim: int = 1,
) -> PersistenceDiagram:
    """Compute the persistence diagram of a Vietoris-Rips complex on `points`."""
    if points.ndim != 2:
        raise ValueError("points must be a 2-D matrix")
    if points.shape[0] < 2:
        return PersistenceDiagram(
            h0=np.zeros((0, 2), dtype=np.float64),
            h1=np.zeros((0, 2), dtype=np.float64),
        )
    result = ripser(points, maxdim=max_dim)
    diagrams = result["dgms"]
    return PersistenceDiagram(
        h0=np.asarray(diagrams[0], dtype=np.float64),
        h1=(
            np.asarray(diagrams[1], dtype=np.float64)
            if len(diagrams) > 1
            else np.zeros((0, 2), dtype=np.float64)
        ),
    )


def persistence_lifetimes(diagram: NDArray[np.float64]) -> NDArray[np.float64]:
    """Death minus birth for each feature. Inf-survival points return inf."""
    if diagram.size == 0:
        return np.empty(0, dtype=np.float64)
    return diagram[:, 1] - diagram[:, 0]


def total_persistence(diagram: NDArray[np.float64], *, ignore_infinite: bool = True) -> float:
    """Σ (death − birth) — a scalar "amount of topology" summary."""
    lifetimes = persistence_lifetimes(diagram)
    if ignore_infinite:
        lifetimes = lifetimes[np.isfinite(lifetimes)]
    return float(lifetimes.sum()) if lifetimes.size > 0 else 0.0
