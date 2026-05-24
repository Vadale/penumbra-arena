"""ℓ-diversity — k-anonymity plus ≥ ℓ distinct sensitive values per bucket.

Concept taught: k-anonymity by itself is vulnerable to the *homogeneity
attack* — if every record in a k-bucket has the same sensitive value
(e.g. "all 7 patients in zip=941xx with age=45 have cancer"), the
adversary recovers the sensitive attribute exactly. ℓ-diversity adds
the requirement that each bucket contains at least ℓ *distinct* values
on a designated sensitive column.

The defender now pays in two ways:
1. Larger suppression rate than vanilla k-anonymity (the constraint is
   strictly tighter).
2. Possible information leakage if ℓ is small relative to the prior of
   the sensitive attribute (the *skewness attack*; t-closeness fixes
   this and is left as a future module).

API mirrors :mod:`penumbra_crypto.defenses.k_anonymity`: a pure
function returning a filtered list, plus an evaluation routine and a
demo. Suppression — not generalisation — is the mechanism.

References
----------
- Machanavajjhala et al. "ℓ-diversity: Privacy beyond k-anonymity"
  (ICDE 2006).
- Li, Li & Venkatasubramanian "t-closeness: Privacy Beyond k-anonymity
  and ℓ-diversity" (ICDE 2007) — the sequel that motivates the
  upgrade path.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class LDiversityReport:
    """Privacy-utility tradeoff snapshot for an ℓ-diversity pass."""

    k: int
    l: int
    n_input: int
    n_released: int
    n_suppressed: int
    n_buckets: int
    suppression_rate: float
    min_distinct_sensitive: int
    homogeneity_safe: bool


def _bucket_key(record: Mapping[str, Any], quasi_identifiers: Sequence[str]) -> tuple[Any, ...]:
    return tuple(record.get(qi) for qi in quasi_identifiers)


def l_diversify(
    records: Sequence[Mapping[str, Any]],
    quasi_id_cols: Sequence[str],
    sensitive_col: str,
    l: int,
    *,
    k: int | None = None,
) -> list[dict[str, Any]]:
    """Return records s.t. each bucket has ≥ k members AND ≥ ℓ distinct sensitive values.

    ``k`` defaults to ``l`` (the minimum k that can be ℓ-diverse). Pass
    a larger k explicitly to stack the two thresholds — e.g. k=10, ℓ=4.

    The function is pure: input records are never mutated; only those
    whose bucket satisfies both constraints survive. Empty input ⇒
    empty output.
    """
    if l < 1:
        raise LDiversityError(f"l must be >= 1, got {l}")
    if not quasi_id_cols:
        raise LDiversityError("quasi_id_cols must be non-empty")
    if not sensitive_col:
        raise LDiversityError("sensitive_col must be non-empty")
    effective_k = max(k if k is not None else l, l)
    if not records:
        return []

    buckets: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for idx, rec in enumerate(records):
        buckets[_bucket_key(rec, quasi_id_cols)].append(idx)

    kept: list[dict[str, Any]] = []
    for indices in buckets.values():
        if len(indices) < effective_k:
            continue
        distinct_sensitive = {records[i].get(sensitive_col) for i in indices}
        if len(distinct_sensitive) < l:
            continue
        for i in indices:
            kept.append(dict(records[i]))
    return kept


def evaluate_tradeoff(
    records: Sequence[Mapping[str, Any]],
    quasi_id_cols: Sequence[str],
    sensitive_col: str,
    l: int,
    *,
    k: int | None = None,
) -> LDiversityReport:
    """Privacy-utility metrics for an ℓ-diversity release.

    Privacy headline: ``min_distinct_sensitive`` — the smallest number
    of distinct sensitive values across surviving buckets (always ≥ ℓ
    by construction). The adversary's best confidence on the sensitive
    attribute is bounded by ``1 / l`` under the simple counting model.

    Utility cost: ``suppression_rate``, which is monotone non-decreasing
    in ℓ for a fixed k.
    """
    effective_k = max(k if k is not None else l, l)
    released = l_diversify(records, quasi_id_cols, sensitive_col, l, k=effective_k)
    n_input = len(records)
    n_released = len(released)

    by_bucket: dict[tuple[Any, ...], set[Any]] = defaultdict(set)
    for r in released:
        by_bucket[_bucket_key(r, quasi_id_cols)].add(r.get(sensitive_col))
    min_distinct = min((len(v) for v in by_bucket.values()), default=0)

    return LDiversityReport(
        k=effective_k,
        l=l,
        n_input=n_input,
        n_released=n_released,
        n_suppressed=n_input - n_released,
        n_buckets=len(by_bucket),
        suppression_rate=((n_input - n_released) / n_input) if n_input else 0.0,
        min_distinct_sensitive=min_distinct,
        homogeneity_safe=(min_distinct >= l) and (n_released > 0),
    )


def demo() -> dict[str, object]:
    """Self-contained demo: sweep ℓ → (suppression, homogeneity safety)."""
    import numpy as np

    rng = np.random.default_rng(seed=20260523)
    n = 400
    records: list[dict[str, Any]] = [
        {
            "city": str(rng.choice(["A", "B", "C", "D", "E"])),
            "product": str(rng.choice(["food", "tools", "luxury", "medicine"])),
            "agent_id": int(rng.integers(0, 50)),
            "diagnosis": str(rng.choice(["a", "b", "c", "d"])),
        }
        for _ in range(n)
    ]
    curve: list[dict[str, float]] = []
    k = 5
    for l in (1, 2, 3, 4):
        report = evaluate_tradeoff(records, ["city", "product"], "diagnosis", l, k=k)
        curve.append(
            {
                "l": float(l),
                "k": float(report.k),
                "suppression_rate": report.suppression_rate,
                "min_distinct_sensitive": float(report.min_distinct_sensitive),
                "homogeneity_safe": 1.0 if report.homogeneity_safe else 0.0,
                "n_released": float(report.n_released),
            }
        )
    return {
        "available": True,
        "algorithm": "l-diversity (suppression)",
        "quasi_identifiers": ["city", "product"],
        "sensitive": "diagnosis",
        "k": k,
        "n_input": n,
        "curve": curve,
    }


class LDiversityError(ValueError):
    """Raised on invalid ℓ-diversity parameters."""
