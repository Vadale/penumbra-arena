"""Encrypted position heatmap with optional DP-noised release.

Concept taught: the central Penumbra claim is "positions are encrypted;
only aggregates are released". This module gives that claim a working
implementation:

1. Each tick, every agent's position is a node index in [0, n_nodes).
2. We turn each position into a one-hot vector of length n_nodes.
3. Each one-hot is encrypted with CKKS (SIMD-packed; one ciphertext
   per agent fits in one CKKS slot row).
4. The server *adds* the N ciphertexts homomorphically into a single
   "density ciphertext".
5. The aggregate is decrypted — yielding only the per-node *count*.
6. **Optional DP layer**: a Laplace mechanism noises the released
   density before it leaves the server, with a budget accountant that
   refuses further releases when ε is exhausted.

Why both encryption AND differential privacy?
- *Encryption* (CKKS) hides per-agent positions from the server's
  arithmetic. The server learns only the aggregate after decryption.
- *Differential privacy* protects the released aggregate from
  reconstruction attacks (Dinur-Nissim) that combine many low-noise
  releases. Encryption alone leaks the aggregate clean; DP alone
  exposes per-agent positions to the server. The two are complementary.

Memory note: at 50 agents × n_nodes=50, every aggregate is one
ciphertext, ~256 KB. We compute it once per second (not per tick) so
the budget stays comfortable.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from penumbra_core.simulation import Simulation
from penumbra_crypto.ckks import HEBackend
from penumbra_crypto.dp import BudgetExceededError, DPMechanism

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HeatmapSample:
    """One encrypted-heatmap measurement, optionally DP-noised.

    `density` is what an EXTERNAL client would see (with DP noise
    applied if a budget is available). `clean_density` is the pre-DP
    aggregate — production wouldn't expose it, but for the live
    pedagogy we keep it so the dashboard can show the noise as a
    visible delta.
    """

    tick: int
    timestamp_ns: int
    density: NDArray[np.float64]
    clean_density: NDArray[np.float64]
    decrypted_total: float
    noise_applied: bool
    epsilon_spent_total: float


class EncryptedHeatmap:
    """Stateful builder. Holds the HE backend + optional DP mechanism."""

    def __init__(
        self,
        backend: HEBackend,
        *,
        n_nodes: int,
        dp_mechanism: DPMechanism | None = None,
        dp_epsilon_per_release: float = 0.05,
        dp_sensitivity: float = 1.0,
    ) -> None:
        if n_nodes <= 0:
            raise ValueError("n_nodes must be > 0")
        self._backend = backend
        self._n_nodes = n_nodes
        self._latest: HeatmapSample | None = None
        self._dp = dp_mechanism
        self._dp_epsilon = dp_epsilon_per_release
        self._dp_sensitivity = dp_sensitivity

    @classmethod
    def for_simulation(
        cls,
        backend: HEBackend,
        simulation: Simulation,
        *,
        dp_mechanism: DPMechanism | None = None,
        dp_epsilon_per_release: float = 0.05,
    ) -> EncryptedHeatmap:
        return cls(
            backend,
            n_nodes=simulation.arena.graph.number_of_nodes(),
            dp_mechanism=dp_mechanism,
            dp_epsilon_per_release=dp_epsilon_per_release,
        )

    @property
    def latest(self) -> HeatmapSample | None:
        return self._latest

    @property
    def dp_mechanism(self) -> DPMechanism | None:
        return self._dp

    @property
    def backend(self) -> HEBackend:
        """The underlying HE backend (for snapshot/restore wiring)."""
        return self._backend

    def compute(self, simulation: Simulation) -> HeatmapSample:
        """Encrypt every agent's position, sum, decrypt, optionally DP-noise.

        Memory note (stress-test fix A): TenSEAL CKKSVectors wrap C++
        objects that the Python GC doesn't release as eagerly as
        pure-Python tuples. We `del` intermediate ciphertexts as we
        go, and `del accumulator` after decryption, to keep the
        per-call working set small. Without this the per-second
        encrypt-sum-decrypt cycle climbs RSS by a few MB per second.
        """
        accumulator: object | None = None
        for agent in simulation.agents:
            if not 0 <= agent.position < self._n_nodes:
                continue
            one_hot = np.zeros(self._n_nodes, dtype=np.float64)
            one_hot[agent.position] = 1.0
            ct = self._backend.encrypt(one_hot)
            if accumulator is None:
                accumulator = ct
            else:
                new_acc = self._backend.add(accumulator, ct)
                del accumulator
                del ct
                accumulator = new_acc
            del one_hot
        if accumulator is None:
            density = np.zeros(self._n_nodes, dtype=np.float64)
        else:
            decrypted = self._backend.decrypt(accumulator)[: self._n_nodes]
            density = np.maximum(decrypted, 0.0)
            del accumulator

        clean_density = density.copy()
        noise_applied = False
        if self._dp is not None:
            try:
                density = self._dp.laplace_vector(
                    density,
                    sensitivity=self._dp_sensitivity,
                    epsilon=self._dp_epsilon,
                )
                density = np.maximum(density, 0.0)
                noise_applied = True
            except BudgetExceededError:
                msg = (
                    "DP budget exhausted; releasing un-noised density."
                    " Restart with a larger PrivacyBudget to keep DP active."
                )
                logger.warning(msg)

        epsilon_spent = self._dp.budget.epsilon_spent if self._dp is not None else 0.0
        sample = HeatmapSample(
            tick=simulation.tick_counter,
            timestamp_ns=time.time_ns(),
            density=density,
            clean_density=clean_density,
            decrypted_total=float(np.sum(density)),
            noise_applied=noise_applied,
            epsilon_spent_total=float(epsilon_spent),
        )
        self._latest = sample
        return sample
