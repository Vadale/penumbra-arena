"""Flush+Reload cache-timing side-channel against CKKS operations.

Concept taught: secret-dependent memory access patterns create timing
differences observable via CPU cache. The classical Flush+Reload attack
(Yarom & Falkner 2014) flushes a target cache line, lets the victim
operate, then times a reload — fast = victim hit the line, slow =
miss. Repeated against CKKS multiplications, an attacker who learns
*which slots are non-zero* can infer parts of the plaintext.

We simulate this in software (no hardware perf counters in pytest):
record per-op latency with two ciphertext shapes (sparse vs dense)
and Welch t-test the distributions. Modern CKKS implementations
(TenSEAL, OpenFHE) operate on the full polynomial regardless of
slot sparsity, so the observed timing is *statistically
indistinguishable* between shapes — the attack must FAIL.

Defence
-------
Constant-time ring arithmetic in the HE backend. Both TenSEAL and
OpenFHE pad to the full polynomial degree on every op. Penumbra's
hot path (CKKS add + mul) inherits this guarantee.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import ttest_ind


@dataclass(frozen=True, slots=True)
class AttackResult:
    """Standard envelope: did the attack succeed + structured evidence."""

    success: bool
    evidence: Mapping[str, object] = field(default_factory=dict)


def attack(
    ckks_operation: Callable[[np.ndarray], object],
    *,
    n_samples: int = 1000,
    vector_size: int = 64,
    t_stat_threshold: float = 6.0,
) -> AttackResult:
    """Time `ckks_operation` on sparse vs dense inputs; Welch-test the gap.

    The operation should be a callable taking a numpy vector and
    performing one CKKS-side operation (e.g. encrypt + add). On a
    constant-time implementation `|t| < threshold` and we report
    `leak_detected = False`.
    """
    sparse = np.zeros(vector_size, dtype=np.float64)
    sparse[0] = 1.0
    dense = np.ones(vector_size, dtype=np.float64)

    sparse_ns: list[float] = []
    dense_ns: list[float] = []
    # Interleave to defuse drift (background load, thermal, JIT).
    for _ in range(n_samples):
        t0 = time.perf_counter_ns()
        _ = ckks_operation(sparse)
        sparse_ns.append(float(time.perf_counter_ns() - t0))
        t0 = time.perf_counter_ns()
        _ = ckks_operation(dense)
        dense_ns.append(float(time.perf_counter_ns() - t0))

    sparse_arr = np.asarray(sparse_ns)
    dense_arr = np.asarray(dense_ns)
    result = ttest_ind(sparse_arr, dense_arr, equal_var=False)
    welch_t = float(result.statistic)  # pyright: ignore[reportAttributeAccessIssue]
    p = float(result.pvalue)  # pyright: ignore[reportAttributeAccessIssue]
    leak = abs(welch_t) > t_stat_threshold
    return AttackResult(
        success=leak,
        evidence={
            "welch_t": welch_t,
            "p_value": p,
            "leak_detected": bool(leak),
            "sparse_median_us": float(np.median(sparse_arr) / 1_000.0),
            "dense_median_us": float(np.median(dense_arr) / 1_000.0),
            "n_samples": n_samples,
        },
    )


def demo(*, n_samples: int = 200, vector_size: int = 64) -> dict[str, object]:
    """Time TenSEAL add over sparse vs dense ciphertexts. Should NOT leak."""
    try:
        from penumbra_crypto.ckks import TenSEALBackend
    except ImportError:
        return {
            "available": False,
            "reason": "TenSEAL backend unavailable",
        }

    backend = TenSEALBackend()

    def _op(vec: np.ndarray) -> object:
        ct = backend.encrypt(vec)
        return backend.add(ct, ct)

    result = attack(_op, n_samples=n_samples, vector_size=vector_size)
    return {
        "available": True,
        "algorithm": "Flush+Reload-style timing (simulated) on TenSEAL CKKS add",
        "n_samples": n_samples,
        "vector_size": vector_size,
        "welch_t": result.evidence["welch_t"],
        "p_value": result.evidence["p_value"],
        "leak_detected": result.evidence["leak_detected"],
        "sparse_median_us": result.evidence["sparse_median_us"],
        "dense_median_us": result.evidence["dense_median_us"],
        "success": result.success,
        "expectation": "constant-time backend → leak_detected = False",
        "defence_hint": "Constant-time ring arithmetic in TenSEAL/OpenFHE pads to full poly degree",
    }
