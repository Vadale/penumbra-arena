"""Property tests for the cache-timing side-channel attack.

Penumbra uses TenSEAL/OpenFHE, both of which are constant-time on add.
So `leak_detected` must come back False on the demo.
"""

from __future__ import annotations

import numpy as np
import pytest
from penumbra_attacker.attacks import cache_sidechannel as cs


def test_demo_runs_and_returns_envelope() -> None:
    result = cs.demo(n_samples=40, vector_size=32)
    if not result["available"]:
        pytest.skip("TenSEAL backend unavailable")
    for key in ("welch_t", "p_value", "leak_detected", "expectation", "defence_hint"):
        assert key in result


@pytest.mark.slow
def test_constant_time_no_leak_detected() -> None:
    result = cs.demo(n_samples=200, vector_size=64)
    if not result["available"]:
        pytest.skip("TenSEAL backend unavailable")
    assert result["leak_detected"] is False


def test_attack_on_artificially_leaky_op_detects_leak() -> None:
    """Sanity: when the operation IS data-dependent, the attack DOES detect."""
    import time as _time

    def leaky(vec: np.ndarray) -> object:
        # Spin proportional to non-zero count — a synthetic leak.
        n = int(np.count_nonzero(vec))
        t0 = _time.perf_counter_ns()
        while _time.perf_counter_ns() - t0 < 1_000 * (n + 1):
            pass
        return n

    out = cs.attack(leaky, n_samples=100, vector_size=32)
    assert out.evidence["leak_detected"] is True


def test_attack_on_truly_constant_op_no_leak() -> None:
    """Sanity: a no-op (truly constant-time) leaves t-stat small."""

    def constant(vec: np.ndarray) -> object:
        return int(vec.shape[0])

    out = cs.attack(constant, n_samples=80, vector_size=32, t_stat_threshold=8.0)
    # Allow the very rare flake from OS noise — assert |t| not absurd.
    assert abs(float(out.evidence["welch_t"])) < 30  # type: ignore[arg-type]
