"""Linear algebra on the arena graph: Laplacian, spectral embedding.

Concept taught: a graph's *Laplacian* L = D - A (D = degree matrix, A
= adjacency) encodes the graph's connectivity in its spectrum. The
smallest eigenvalue is always 0 (constant vector); the second smallest
("Fiedler value") quantifies how connected the graph is, and its
eigenvector is the optimal continuous relaxation of the minimum-cut
partition.

Spectral clustering uses the bottom k eigenvectors as coordinates and
runs k-means in that space. For Penumbra this gives us *factions* —
clusters of agents whose movement is correlated, even when individual
positions are encrypted (we work on the public coalition-graph
adjacency that Phase 2 produces).

References
- Chung, "Spectral Graph Theory" (1997), chapter 1.
- von Luxburg, "A tutorial on spectral clustering" (Stat. Comput. 2007).
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import eigsh
from sklearn.cluster import KMeans


@dataclass(frozen=True, slots=True)
class SpectralResult:
    """Result of a spectral embedding."""

    eigenvalues: NDArray[np.float64]
    embedding: NDArray[np.float64]  # shape (n_nodes, k)
    laplacian_kind: str


def normalized_laplacian(graph: nx.Graph) -> csr_matrix:
    """Symmetric normalised Laplacian L_sym = I - D^{-1/2} A D^{-1/2}.

    Symmetric (so eigsh is fast and stable) and scale-invariant to the
    overall graph "size", which is what we want for clustering.
    """
    return cast_csr(nx.normalized_laplacian_matrix(graph).astype(np.float64))


def spectral_embedding(graph: nx.Graph, *, k: int = 4) -> SpectralResult:
    """Embed the graph into ℝ^k via the bottom k Laplacian eigenvectors.

    Uses `sigma=0, which="LM"` shift-invert to robustly extract the
    smallest eigenvalues (a common Lanczos pitfall: `which="SM"`
    converges slowly near zero). The first eigenvector (constant) is
    dropped; we return the next k.
    """
    if graph.number_of_nodes() <= k:
        raise ValueError("k must be smaller than the number of nodes")
    laplacian = normalized_laplacian(graph)
    eigenvalues, eigenvectors = eigsh(laplacian, k=k + 1, sigma=0, which="LM")
    order = np.argsort(eigenvalues)
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]
    return SpectralResult(
        eigenvalues=np.asarray(eigenvalues[1 : k + 1], dtype=np.float64),
        embedding=np.asarray(eigenvectors[:, 1 : k + 1], dtype=np.float64),
        laplacian_kind="normalized-symmetric",
    )


def spectral_clusters(graph: nx.Graph, *, n_clusters: int = 4) -> NDArray[np.intp]:
    """Spectral clustering: Ng-Jordan-Weiss algorithm.

    Row-normalise the embedding to lie on the unit sphere before
    k-means — without this step, k-means in raw eigenvector space
    misclusters even simple two-clique graphs (Ng et al., NIPS 2002).
    """
    embedding = spectral_embedding(graph, k=n_clusters).embedding
    norms = np.linalg.norm(embedding, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # avoid divide-by-zero for the constant vector
    normalised = embedding / norms
    km = KMeans(n_clusters=n_clusters, n_init=10, random_state=0)  # pyright: ignore[reportArgumentType]
    return np.asarray(km.fit_predict(normalised), dtype=np.intp)


def algebraic_connectivity(graph: nx.Graph) -> float:
    """Fiedler value — the algebraic connectivity. 0 ⇔ disconnected."""
    if graph.number_of_nodes() < 2:
        return 0.0
    laplacian = normalized_laplacian(graph)
    eigenvalues, _ = eigsh(laplacian, k=2, which="SM")
    return float(np.sort(eigenvalues)[1])


def cast_csr(matrix: object) -> csr_matrix:
    """Helper to widen networkx return types (which annotate loosely)."""
    return matrix  # type: ignore[return-value]
