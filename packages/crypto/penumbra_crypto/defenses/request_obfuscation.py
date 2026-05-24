"""Request obfuscation — Bonferroni correction + dummy-query injection.

Concept taught: an adversary issuing many DP queries gets two ways to
amplify its leakage:
1. *Family-wise error inflation* — running k queries with per-query
   α = 0.05 yields a family-wise false-positive rate ≈ 1 - (1-α)^k.
   Bonferroni correction forces each query to its own α/k, costing the
   adversary more privacy budget per useful answer.
2. *Cheap probing* — repeated near-identical queries refine the
   adversary's posterior. Mixing dummy queries into the stream raises
   the noise floor of any aggregation the adversary attempts.

The defender pays a small accounting overhead (per-query ε scales as
1/k under Bonferroni) for a strictly larger drain on the adversary's
budget. Dummy queries cost only bandwidth — they are answered with
sampled-from-distribution placeholders that consume no real privacy
budget.

API is pure-functional. ``bonferroni_correct_queries`` returns a list
of corrected ε per query under a chosen family-wise rate.
``add_dummy_queries`` returns an interleaved list with ``n_dummies``
plausible fakes mixed into the real queries.

References
----------
- Bonferroni "Teoria statistica delle classi e calcolo delle
  probabilità" (1936). The original union bound.
- Dwork & Rothblum "Concentrated Differential Privacy" (2016) — modern
  composition lower bounds the adversary can't escape.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

DUMMY_FLAG: str = "is_dummy"


@dataclass(slots=True, frozen=True)
class ObfuscationReport:
    """Privacy-utility tradeoff snapshot for an obfuscation pass."""

    n_real_queries: int
    n_dummy_queries: int
    family_size: int
    family_wise_epsilon: float
    per_query_epsilon_corrected: float
    attacker_budget_inflation: float
    dummy_query_rate: float


def _secure_rng() -> np.random.Generator:
    seed = int.from_bytes(secrets.token_bytes(8), "big")
    return np.random.default_rng(seed)


def bonferroni_correct_queries(
    queries: Sequence[Mapping[str, Any]],
    family_size: int | None = None,
    *,
    family_wise_epsilon: float = 1.0,
) -> list[dict[str, Any]]:
    """Annotate each query with a Bonferroni-corrected ε.

    Returns a list of new dicts (the input is not mutated). Each output
    carries the original query plus:
    - ``epsilon_corrected``: the per-query ε under Bonferroni
      (= ``family_wise_epsilon / max(family_size, len(queries))``).
    - ``family_size``: the divisor that was used.

    The adversary that wants to maintain a family-wise ε guarantee MUST
    accept the smaller per-query budget; under Penumbra's DP accountant,
    this drains its total budget ``family_size``× faster than naive
    per-query accounting.
    """
    if family_wise_epsilon <= 0:
        raise ObfuscationError(f"family_wise_epsilon must be > 0, got {family_wise_epsilon}")
    if not queries:
        return []
    k = max(family_size if family_size is not None else len(queries), len(queries))
    corrected_eps = family_wise_epsilon / k
    return [{**dict(q), "epsilon_corrected": corrected_eps, "family_size": k} for q in queries]


def add_dummy_queries(
    real_queries: Sequence[Mapping[str, Any]],
    n_dummies: int,
    *,
    rng: np.random.Generator | None = None,
) -> list[dict[str, Any]]:
    """Interleave ``n_dummies`` decoy queries among ``real_queries``.

    Real queries are annotated ``DUMMY_FLAG=False``; dummies are
    synthesised by resampling each field from the empirical distribution
    of the real queries (so a naive attacker can't filter by schema or
    range) and annotated ``DUMMY_FLAG=True``. Output order is shuffled.

    Defender-side consumers filter on ``DUMMY_FLAG``; attackers that
    don't recognise the flag waste their analysis on every dummy.
    """
    if n_dummies < 0:
        raise ObfuscationError(f"n_dummies must be >= 0, got {n_dummies}")
    if not real_queries:
        return []
    rng = rng if rng is not None else _secure_rng()
    fields = list(real_queries[0].keys())
    if DUMMY_FLAG in fields:
        raise ObfuscationError(f"queries already contain a {DUMMY_FLAG!r} field")
    by_field: dict[str, list[Any]] = {f: [q[f] for q in real_queries] for f in fields}

    annotated_real: list[dict[str, Any]] = [{**dict(q), DUMMY_FLAG: False} for q in real_queries]
    dummies: list[dict[str, Any]] = []
    for _ in range(n_dummies):
        d: dict[str, Any] = {f: by_field[f][int(rng.integers(0, len(by_field[f])))] for f in fields}
        d[DUMMY_FLAG] = True
        dummies.append(d)
    combined = annotated_real + dummies
    perm = rng.permutation(len(combined))
    return [combined[int(i)] for i in perm]


def evaluate_tradeoff(
    real_queries: Sequence[Mapping[str, Any]],
    n_dummies: int,
    family_wise_epsilon: float = 1.0,
    *,
    rng: np.random.Generator | None = None,
) -> ObfuscationReport:
    """Combined Bonferroni + dummy-injection tradeoff.

    ``attacker_budget_inflation`` is the factor by which the attacker's
    naive budget accounting underestimates the true drain — equal to
    ``family_size``, capped at the released stream length.
    """
    if not real_queries:
        raise ObfuscationError("real_queries must be non-empty for evaluation")
    rng = rng if rng is not None else _secure_rng()
    interleaved = add_dummy_queries(real_queries, n_dummies, rng=rng)
    n_real = sum(1 for q in interleaved if not q.get(DUMMY_FLAG, False))
    n_dummy = len(interleaved) - n_real
    family_size = max(len(interleaved), 1)
    per_query = family_wise_epsilon / family_size
    return ObfuscationReport(
        n_real_queries=n_real,
        n_dummy_queries=n_dummy,
        family_size=family_size,
        family_wise_epsilon=family_wise_epsilon,
        per_query_epsilon_corrected=per_query,
        attacker_budget_inflation=float(family_size),
        dummy_query_rate=(n_dummy / max(n_real, 1)),
    )


def demo() -> dict[str, object]:
    """Self-contained demo: sweep dummy rate → attacker inflation curve."""
    rng = np.random.default_rng(seed=20260523)
    n_real = 20
    real_queries = [
        {
            "target_agent": int(rng.integers(0, 50)),
            "metric": str(rng.choice(["wealth", "position", "trades"])),
            "epsilon_request": float(rng.uniform(0.01, 0.2)),
        }
        for _ in range(n_real)
    ]
    curve: list[dict[str, float]] = []
    for n_dummies in (0, 5, 10, 20, 40, 80):
        report = evaluate_tradeoff(
            real_queries,
            n_dummies,
            family_wise_epsilon=1.0,
            rng=np.random.default_rng(seed=7),
        )
        curve.append(
            {
                "n_dummies": float(n_dummies),
                "family_size": float(report.family_size),
                "per_query_epsilon_corrected": report.per_query_epsilon_corrected,
                "attacker_budget_inflation": report.attacker_budget_inflation,
                "dummy_query_rate": report.dummy_query_rate,
            }
        )
    return {
        "available": True,
        "algorithm": "Bonferroni correction + dummy queries",
        "n_real_queries": n_real,
        "family_wise_epsilon": 1.0,
        "curve": curve,
    }


class ObfuscationError(ValueError):
    """Raised on invalid obfuscation parameters or schema conflicts."""
