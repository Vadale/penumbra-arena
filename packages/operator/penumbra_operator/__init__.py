"""Penumbra Operator Mode — Phase 6b Tier 1.

Concept taught: a tabletop drill is a reproducible exercise. The
operator agent is a regular ``Agent`` slot (id = ``n_agents``) that
the simulation drives through the same code paths as the MAPPO
agents; the only difference is that its actions come from an
``OperatorQueue`` populated by a human (CLI ``pno`` or, in Tier 2,
the Operator Console) rather than a learned policy.

This top-level module exposes the small surface a transport-layer
wire-up needs:

- :class:`OperatorAction` / :class:`OperatorActionResult` — the
  dataclasses every action handler exchanges.
- :class:`OperatorQueue` — thread-safe FIFO with
  :meth:`OperatorQueue.pop_due` for the orchestrator's per-tick drain.
- :class:`OperatorScoreCard` — composite scoring snapshot.
- :class:`OperatorContext` — handler input bundle (sim, market,
  mempool, dp mechanism, keystore, operator agent id).
- :func:`apply_action` — single entry point that dispatches an
  action onto its handler with the 50 ms time-budget enforced.

Out of scope for Tier 1: attack actions (Tier 3), defense actions
(Tier 4), Operator Console UI (Tier 2), scenarios (Tier 5),
replay log (Tier 6).
"""

from __future__ import annotations

from penumbra_operator.actions import (
    OperatorAction,
    OperatorActionError,
    OperatorActionResult,
    OperatorContext,
    apply_action,
)
from penumbra_operator.queue import OperatorQueue
from penumbra_operator.replay import (
    SessionLogError,
    SessionLogger,
    replay,
    scorecard_diff,
)
from penumbra_operator.scenarios import (
    Scenario,
    ScenarioError,
    ScenarioRunner,
    ScenarioSession,
    load_scenarios,
)
from penumbra_operator.scoring import OperatorScoreCard

__all__ = [
    "OperatorAction",
    "OperatorActionError",
    "OperatorActionResult",
    "OperatorContext",
    "OperatorQueue",
    "OperatorScoreCard",
    "Scenario",
    "ScenarioError",
    "ScenarioRunner",
    "ScenarioSession",
    "SessionLogError",
    "SessionLogger",
    "apply_action",
    "load_scenarios",
    "replay",
    "scorecard_diff",
]
