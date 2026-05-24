"""Defensive data poisoning — inject decoy traces into released records.

Concept taught: an attacker that fits a model to a leaked trace is only
as accurate as the trace is clean. If the defender mixes in a controlled
fraction of *plausible* decoys, the attacker's model fits a contaminated
distribution and its predictions drift. The strategy mirrors honeypots:
the defender pays a small utility cost (downstream consumers must filter
decoys) for a larger attacker cost (re-identification accuracy falls).

The tradeoff is a curve. At a poisoning rate ``p``, an attacker that
trusts every released record has its accuracy upper-bounded by ``1 - p``
on the decoy points. The defender's utility cost on a downstream
analytics task that ignores the ``is_decoy`` flag scales roughly
linearly in ``p`` for moment statistics (mean / variance).

API is functional and operates on a list of dicts (records); the input
is never mutated in place. Decoys are sampled from per-field empirical
distributions so they look plausible to a naive attacker.

References
----------
- Steinhardt et al. "Certified Defenses for Data Poisoning Attacks"
  (NeurIPS 2017). Adversarial poisoning is the symmetric problem;
  here we use poisoning DEFENSIVELY.
- Honeyfile literature (Yuill et al., 2004) — same idea applied to
  file-system canaries.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

DECOY_FLAG: str = "is_decoy"


@dataclass(slots=True, frozen=True)
class PoisoningReport:
    """Privacy-utility tradeoff snapshot for a single poisoning pass."""

    n_real: int
    n_decoy: int
    poisoning_rate: float
    attacker_max_accuracy: float
    utility_mean_shift: float
    utility_std_shift: float


def _secure_rng() -> np.random.Generator:
    """A CSPRNG-seeded Generator (see ``penumbra_crypto.dp.secure_rng``)."""
    seed = int.from_bytes(secrets.token_bytes(8), "big")
    return np.random.default_rng(seed)


def _sample_decoy_value(values: Sequence[Any], rng: np.random.Generator) -> Any:
    """Resample a single value from the empirical distribution of ``values``.

    Categorical and numeric values are both handled uniformly by drawing
    a random index. Plausibility — not perfect distributional matching —
    is the goal: the attacker must not be able to spot decoys by a trivial
    range check.
    """
    if len(values) == 0:
        return None
    idx = int(rng.integers(0, len(values)))
    return values[idx]


def inject_decoy_traces(
    real_records: Sequence[Mapping[str, Any]],
    rate: float = 0.05,
    *,
    rng: np.random.Generator | None = None,
) -> list[dict[str, Any]]:
    """Return ``real_records`` interleaved with sampled decoys.

    Each record is a flat ``dict``. The output contains every real
    record (unchanged plus a ``DECOY_FLAG=False`` key) and an extra
    ``ceil(rate * len(real))`` decoy records sampled per-field from the
    empirical distribution of the real records. The order is shuffled
    so the attacker can't recover the real subset by position.

    ``rate`` must be in ``[0, 1]``. The decoys carry ``DECOY_FLAG=True``
    so defender-side consumers can filter them; an attacker that ignores
    that flag (the assumed threat model) sees a contaminated stream.
    """
    if not 0.0 <= rate <= 1.0:
        raise PoisoningError(f"rate must be in [0, 1], got {rate}")
    if not real_records:
        return []
    rng = rng if rng is not None else _secure_rng()

    n_real = len(real_records)
    n_decoy = int(np.ceil(rate * n_real))
    fields = list(real_records[0].keys())
    if DECOY_FLAG in fields:
        raise PoisoningError(f"records already contain a {DECOY_FLAG!r} field")

    by_field: dict[str, list[Any]] = {f: [r[f] for r in real_records] for f in fields}

    annotated_real: list[dict[str, Any]] = [{**dict(r), DECOY_FLAG: False} for r in real_records]
    decoys: list[dict[str, Any]] = []
    for _ in range(n_decoy):
        decoy: dict[str, Any] = {f: _sample_decoy_value(by_field[f], rng) for f in fields}
        decoy[DECOY_FLAG] = True
        decoys.append(decoy)

    combined = annotated_real + decoys
    perm = rng.permutation(len(combined))
    return [combined[int(i)] for i in perm]


def evaluate_tradeoff(
    real_records: Sequence[Mapping[str, Any]],
    numeric_field: str,
    rate: float = 0.05,
    *,
    rng: np.random.Generator | None = None,
) -> PoisoningReport:
    """Return a measurable privacy-utility tradeoff for a single ``rate``.

    Utility cost is measured as the absolute shift of the mean and std
    of ``numeric_field`` between the raw and the poisoned stream
    (consumer ignores the ``is_decoy`` flag, the worst case for the
    defender). Privacy benefit is bounded by ``1 - rate``: an attacker
    that trusts the released data has at most ``1 - rate`` accuracy on
    average over the contaminated records.
    """
    if not real_records:
        raise PoisoningError("real_records must be non-empty for evaluation")
    rng = rng if rng is not None else _secure_rng()
    poisoned = inject_decoy_traces(real_records, rate=rate, rng=rng)

    real_values = np.array([float(r[numeric_field]) for r in real_records], dtype=np.float64)
    poisoned_values = np.array([float(r[numeric_field]) for r in poisoned], dtype=np.float64)
    n_real = len(real_records)
    n_decoy = len(poisoned) - n_real
    realised_rate = n_decoy / max(n_real, 1)
    return PoisoningReport(
        n_real=n_real,
        n_decoy=n_decoy,
        poisoning_rate=realised_rate,
        attacker_max_accuracy=max(1.0 - realised_rate, 0.0),
        utility_mean_shift=float(abs(np.mean(poisoned_values) - np.mean(real_values))),
        utility_std_shift=float(abs(np.std(poisoned_values) - np.std(real_values))),
    )


def demo() -> dict[str, object]:
    """Self-contained demo returning a sweep of (rate → tradeoff) points.

    Used by the dashboard tile + property tests. Deterministic — uses a
    pinned RNG so the curve is stable across page loads.
    """
    rng = np.random.default_rng(seed=20260523)
    n = 200
    records: list[dict[str, Any]] = [
        {
            "agent_id": int(rng.integers(0, 50)),
            "wealth": float(rng.normal(loc=100.0, scale=20.0)),
            "city": str(rng.choice(["A", "B", "C", "D"])),
        }
        for _ in range(n)
    ]
    curve: list[dict[str, float]] = []
    for rate in (0.0, 0.05, 0.10, 0.20, 0.35, 0.50):
        report = evaluate_tradeoff(
            records, "wealth", rate=rate, rng=np.random.default_rng(seed=1234)
        )
        curve.append(
            {
                "rate": float(rate),
                "attacker_max_accuracy": report.attacker_max_accuracy,
                "utility_mean_shift": report.utility_mean_shift,
                "utility_std_shift": report.utility_std_shift,
                "n_decoy": float(report.n_decoy),
            }
        )
    return {
        "available": True,
        "algorithm": "defensive decoy injection",
        "n_real": n,
        "curve": curve,
    }


class PoisoningError(ValueError):
    """Raised on invalid poisoning parameters or schema conflicts."""
