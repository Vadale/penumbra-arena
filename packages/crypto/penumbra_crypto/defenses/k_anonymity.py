"""k-anonymity — bucket records so every quasi-identifier appears in ≥ k.

Concept taught: Sweeney's 2002 result showed 87% of the US population
is uniquely identified by (zip, gender, birth-date) alone. *k*-anonymity
is the simplest defense: release only records whose quasi-identifier
tuple is shared by at least k-1 others; everything else is suppressed.
The adversary's best re-identification on a released bucket is 1/k.

Two failure modes the user should learn:
1. *Homogeneity attack*: a k-anonymous bucket where every record shares
   the SENSITIVE value still leaks it. ℓ-diversity (sibling module) is
   the standard countermeasure.
2. *Background-knowledge attack*: k-anonymity assumes the adversary
   knows only the quasi-identifiers. If the adversary has additional
   side information, k-anonymity guarantees nothing.

API is pure-functional. ``k_anonymise`` returns a *new* list with
small-bucket records dropped; it never mutates the input. Suppression
is the only mechanism here — generalisation is left to ℓ-diversity
and t-closeness, which the user can layer on.

References
----------
- Sweeney "k-anonymity: a model for protecting privacy" (IJUFKS 2002).
- Machanavajjhala et al. "ℓ-diversity: Privacy beyond k-anonymity"
  (ICDE 2006) — same series, sister module.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class KAnonymityReport:
    """Privacy-utility tradeoff snapshot for a single k-anonymity pass."""

    k: int
    n_input: int
    n_released: int
    n_suppressed: int
    n_buckets: int
    suppression_rate: float
    adversary_max_reidentification: float


def _bucket_key(record: Mapping[str, Any], quasi_identifiers: Sequence[str]) -> tuple[Any, ...]:
    """Hashable tuple of quasi-identifier values for grouping.

    Missing fields default to ``None`` so callers don't crash on partial
    records; the cost is that ``None``-bucket records may aggregate
    distinct populations, which is a defender choice the docs flag.
    """
    return tuple(record.get(qi) for qi in quasi_identifiers)


def k_anonymise(
    records: Sequence[Mapping[str, Any]],
    quasi_identifiers: Sequence[str],
    k: int,
) -> list[dict[str, Any]]:
    """Return only those records whose quasi-id tuple has ≥ ``k`` members.

    Records in undersized buckets are SUPPRESSED (dropped). Output
    preserves input order within the surviving buckets. The function
    is total: empty input ⇒ empty output; k ≤ 1 ⇒ every record passes.
    """
    if k < 1:
        raise KAnonymityError(f"k must be >= 1, got {k}")
    if not quasi_identifiers:
        raise KAnonymityError("quasi_identifiers must be non-empty")
    if not records:
        return []

    buckets: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for idx, rec in enumerate(records):
        buckets[_bucket_key(rec, quasi_identifiers)].append(idx)

    kept: list[dict[str, Any]] = []
    for indices in buckets.values():
        if len(indices) >= k:
            for i in indices:
                kept.append(dict(records[i]))
    return kept


def evaluate_tradeoff(
    records: Sequence[Mapping[str, Any]],
    quasi_identifiers: Sequence[str],
    k: int,
) -> KAnonymityReport:
    """Privacy-utility metrics for a k-anonymity release.

    Privacy: ``adversary_max_reidentification = 1 / k`` — by
    construction every released bucket has ≥ k members, so the best the
    attacker can do on a single quasi-id match is uniform-at-random
    over k.

    Utility cost: ``suppression_rate`` — fraction of input records the
    defender had to drop. The sweep across k is the curve a dashboard
    should show.
    """
    released = k_anonymise(records, quasi_identifiers, k)
    n_input = len(records)
    n_released = len(released)
    n_suppressed = n_input - n_released
    distinct_keys: set[tuple[Any, ...]] = {_bucket_key(r, quasi_identifiers) for r in released}
    return KAnonymityReport(
        k=k,
        n_input=n_input,
        n_released=n_released,
        n_suppressed=n_suppressed,
        n_buckets=len(distinct_keys),
        suppression_rate=(n_suppressed / n_input) if n_input else 0.0,
        adversary_max_reidentification=1.0 / k if k >= 1 else 1.0,
    )


def demo() -> dict[str, object]:
    """Self-contained demo: sweep k → (suppression, adversary advantage)."""
    import numpy as np

    rng = np.random.default_rng(seed=20260523)
    n = 300
    records: list[dict[str, Any]] = [
        {
            "city": str(rng.choice(["A", "B", "C", "D", "E"])),
            "product": str(rng.choice(["food", "tools", "luxury", "medicine"])),
            "agent_id": int(rng.integers(0, 50)),
            "qty": int(rng.integers(1, 10)),
        }
        for _ in range(n)
    ]
    curve: list[dict[str, float]] = []
    for k in (1, 2, 3, 5, 8, 13, 21):
        report = evaluate_tradeoff(records, ["city", "product"], k)
        curve.append(
            {
                "k": float(k),
                "suppression_rate": report.suppression_rate,
                "adversary_max_reidentification": report.adversary_max_reidentification,
                "n_released": float(report.n_released),
                "n_buckets": float(report.n_buckets),
            }
        )
    return {
        "available": True,
        "algorithm": "k-anonymity (suppression)",
        "quasi_identifiers": ["city", "product"],
        "n_input": n,
        "curve": curve,
    }


class KAnonymityError(ValueError):
    """Raised on invalid k-anonymity parameters."""
