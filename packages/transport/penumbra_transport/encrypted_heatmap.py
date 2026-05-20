"""Encrypted position heatmap — the load-bearing CKKS use case.

Concept taught: the central Penumbra claim is "positions are encrypted;
only aggregates are released". This module gives that claim a working
implementation:

1. Each tick, every agent's position is a node index in [0, n_nodes).
2. We turn each position into a one-hot vector of length n_nodes.
3. Each one-hot is encrypted with CKKS (SIMD-packed; one ciphertext
   per agent fits in one CKKS slot row).
4. The server *adds* the N ciphertexts homomorphically into a single
   "density ciphertext".
5. The aggregate is decrypted — yielding only the per-node *count*,
   not the per-agent positions.

Memory note: at 50 agents × n_nodes=50, every aggregate is one
ciphertext, ~256 KB. We compute it once per second (not per tick) so
the budget stays comfortable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from penumbra_core.simulation import Simulation
from penumbra_crypto.ckks import HEBackend


@dataclass(frozen=True, slots=True)
class HeatmapSample:
    """One encrypted-heatmap measurement."""

    tick: int
    timestamp_ns: int
    density: NDArray[np.float64]  # decrypted aggregate; length = n_nodes
    decrypted_total: float  # expected to ≈ n_agents


class EncryptedHeatmap:
    """Stateful builder. Holds the HE backend + the latest decrypted sample."""

    def __init__(self, backend: HEBackend, *, n_nodes: int) -> None:
        if n_nodes <= 0:
            raise ValueError("n_nodes must be > 0")
        self._backend = backend
        self._n_nodes = n_nodes
        self._latest: HeatmapSample | None = None

    @classmethod
    def for_simulation(
        cls,
        backend: HEBackend,
        simulation: Simulation,
    ) -> EncryptedHeatmap:
        return cls(backend, n_nodes=simulation.arena.graph.number_of_nodes())

    @property
    def latest(self) -> HeatmapSample | None:
        return self._latest

    def compute(self, simulation: Simulation) -> HeatmapSample:
        """Encrypt every agent's position, sum ciphertexts, decrypt the aggregate."""
        accumulator: object | None = None
        for agent in simulation.agents:
            if not 0 <= agent.position < self._n_nodes:
                continue
            one_hot = np.zeros(self._n_nodes, dtype=np.float64)
            one_hot[agent.position] = 1.0
            ct = self._backend.encrypt(one_hot)
            accumulator = ct if accumulator is None else self._backend.add(accumulator, ct)
        if accumulator is None:
            density = np.zeros(self._n_nodes, dtype=np.float64)
        else:
            decrypted = self._backend.decrypt(accumulator)[: self._n_nodes]
            # CKKS introduces small approximation noise; clamp negatives that
            # appear as roundoff to 0 for cleanliness in the wire format.
            density = np.maximum(decrypted, 0.0)
        sample = HeatmapSample(
            tick=simulation.tick_counter,
            timestamp_ns=time.time_ns(),
            density=density,
            decrypted_total=float(np.sum(density)),
        )
        self._latest = sample
        return sample
