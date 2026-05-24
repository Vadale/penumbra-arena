"""Operator score card.

Concept taught: a *multi-axis composite* score is what stops a
single-objective optimisation from gaming the rubric. The operator's
profit, privacy-preserved fraction, attacks-survived counter and
chain-contribution counter are weighted into one scalar, but the
per-axis values stay visible so the dashboard can show which axis
the operator is winning (or losing) on.

The default weights are based on the survey-validated weights from
the plan (Tier 5 will swap in scenario-specific weights). Profit is
normalised by ``initial_coins`` so the score stays comparable across
sessions with different starting wallets.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OperatorScoreWeights:
    """Weight per axis of the composite score. Should sum to 1.0."""

    profit: float = 0.40
    privacy_preserved: float = 0.30
    attacks_survived: float = 0.20
    chain_contribution: float = 0.10


DEFAULT_WEIGHTS = OperatorScoreWeights()


@dataclass(frozen=True, slots=True)
class OperatorScoreCard:
    """Snapshot of operator performance across the 4 axes."""

    profit: float
    privacy_preserved: float
    attacks_survived: int
    chain_contribution: int
    composite: float
    weights: OperatorScoreWeights = DEFAULT_WEIGHTS

    @classmethod
    def compute(
        cls,
        *,
        coins_now: float,
        coins_start: float,
        epsilon_spent: float,
        epsilon_total: float,
        attacks_survived: int,
        chain_contribution: int,
        weights: OperatorScoreWeights = DEFAULT_WEIGHTS,
    ) -> OperatorScoreCard:
        """Compute a composite scorecard from raw counters.

        Each axis is clipped to ``[0, 1]`` before being weighted in.
        Profit is the *fractional* return: ``(now - start) / max(start, 1)``,
        clipped to ``[-1, 1]`` and then shifted to ``[0, 1]`` so the
        composite stays bounded. Privacy-preserved is
        ``1 - epsilon_spent / epsilon_total``. Attacks-survived and
        chain-contribution are scaled by a soft cap of 10 events each;
        the dashboard shows the raw counters too.
        """
        if epsilon_total <= 0:
            privacy_preserved = 0.0
        else:
            privacy_preserved = max(0.0, 1.0 - epsilon_spent / epsilon_total)
        denom = coins_start if coins_start > 0 else 1.0
        raw_profit = (coins_now - coins_start) / denom
        profit_normalised = max(0.0, min(1.0, 0.5 + 0.5 * max(-1.0, min(1.0, raw_profit))))
        # Soft cap at 10 events — above that, the axis saturates at 1.0.
        att_norm = max(0.0, min(1.0, attacks_survived / 10.0))
        chain_norm = max(0.0, min(1.0, chain_contribution / 10.0))
        composite = (
            weights.profit * profit_normalised
            + weights.privacy_preserved * privacy_preserved
            + weights.attacks_survived * att_norm
            + weights.chain_contribution * chain_norm
        )
        return cls(
            profit=float(raw_profit),
            privacy_preserved=float(privacy_preserved),
            attacks_survived=int(attacks_survived),
            chain_contribution=int(chain_contribution),
            composite=float(composite),
            weights=weights,
        )


__all__ = ["DEFAULT_WEIGHTS", "OperatorScoreCard", "OperatorScoreWeights"]
