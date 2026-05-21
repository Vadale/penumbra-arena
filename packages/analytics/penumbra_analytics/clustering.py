"""Clustering on arena observations.

Concept taught: two complementary clusterers. **HDBSCAN** (Campello,
Moulavi, Sander 2013) is density-based, finds clusters of varying
density and labels noise as -1 — ideal for trajectory blobs in the
arena. **Spectral clustering** (re-exported from `linalg`) is graph-
based and finds well-cut partitions of a similarity graph.

Reference: Campello et al., "Density-based clustering based on
hierarchical density estimates" (PAKDD 2013).
"""

from __future__ import annotations

from dataclasses import dataclass

import hdbscan
import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class HDBSCANResult:
    labels: NDArray[np.intp]
    probabilities: NDArray[np.float64]
    n_clusters: int
    n_noise: int


def hdbscan_cluster(
    points: NDArray[np.float64],
    *,
    min_cluster_size: int = 5,
    min_samples: int | None = None,
) -> HDBSCANResult:
    """Run HDBSCAN on a 2-D point cloud.

    `points`: shape (n_observations, n_features).
    `min_cluster_size`: smallest cluster size to accept.
    Noise points (no cluster) get label `-1`.
    """
    if points.ndim != 2:
        raise ValueError("expected 2-D point matrix")
    if points.shape[0] < min_cluster_size:
        raise ValueError(
            f"need at least {min_cluster_size} points for the configured min_cluster_size"
        )
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
    )
    labels = clusterer.fit_predict(points)
    probs = np.asarray(clusterer.probabilities_, dtype=np.float64)
    unique = {int(label) for label in labels if label != -1}
    return HDBSCANResult(
        labels=np.asarray(labels, dtype=np.intp),
        probabilities=probs,
        n_clusters=len(unique),
        n_noise=int(np.sum(labels == -1)),
    )
