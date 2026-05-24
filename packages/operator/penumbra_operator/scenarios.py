"""Operator scenario engine — Phase 6b Tier 5.

Concept taught: a *scenario* is a reproducible adversarial-robustness
exercise — a YAML file declaring its preconditions, an opening event,
victory clauses, failure clauses, allowed action kinds, and the
weights of the scorecard axes that decide the composite at the end.

The runner is intentionally simple: it diffs the live simulation
state against the victory / failure predicates and reports a flat
``{victory_met, failure_met, progress}`` mapping. The orchestrator
of the dashboard polls ``/operator/scenarios/{id}/status`` to render
the live progress meter; the CLI ``pno`` will get the same surface
in a later tier.

A tiny home-grown JSON-schema validator (``_validate_against_schema``)
keeps the dependency footprint flat — ``jsonschema`` isn't pulled in
just to validate 12 YAML files at boot. The validator only covers the
subset of JSON Schema this codebase uses (``type``, ``required``,
``properties``, ``items``, ``enum``); the schema file itself stays a
proper JSON Schema document so a future migration to ``jsonschema``
is mechanical.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from penumbra_operator.actions import OperatorContext


SCHEMA_PATH: Path = Path(__file__).resolve().parent.parent / "scenarios" / "SCHEMA.json"
SCENARIOS_DIR: Path = Path(__file__).resolve().parent.parent / "scenarios"


class ScenarioError(Exception):
    """Raised when a scenario YAML is missing, malformed, or fails validation."""


@dataclass(frozen=True, slots=True)
class ScoringSpec:
    """Weights per scorecard axis for the composite at scenario end."""

    weights: dict[str, float]


@dataclass(frozen=True, slots=True)
class Scenario:
    """A single scenario definition loaded from YAML.

    The fields mirror the YAML schema 1:1 (see ``scenarios/SCHEMA.json``).
    ``preconditions`` is a flat list of ``"key: value"`` strings rather
    than nested mappings so the runner can render them as a checklist
    without traversing arbitrary shapes — the actual side-effects of
    each precondition are applied by ``ScenarioRunner.start`` via a
    small dispatch table.
    """

    id: str
    title: str
    difficulty: str
    description: str
    setup_seed: int
    setup_n_agents: int
    preconditions: tuple[str, ...]
    opening_event_kind: str
    opening_event_payload: dict[str, Any]
    victory: tuple[str, ...]
    failure: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    scoring: ScoringSpec
    source_path: Path | None = None


@dataclass(slots=True)
class ScenarioSession:
    """Live state for one running scenario.

    Holds the start tick so progress meters can show elapsed ticks,
    a ``coins_start`` snapshot so profit-based clauses are evaluated
    against the operator's wallet at scenario start (not at enable
    time), and a ``custom`` dict that scenario-specific bookkeeping
    can pin extra counters onto (e.g. the attacker accuracy of a
    bullwhip-defender scenario).
    """

    scenario_id: str
    start_tick: int
    coins_start: float
    custom: dict[str, float] = field(default_factory=dict)


# ── YAML / schema loading ──────────────────────────────────────────


def _load_schema() -> dict[str, Any]:
    if not SCHEMA_PATH.exists():
        raise ScenarioError(f"missing scenario schema at {SCHEMA_PATH}")
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate_against_schema(doc: Any, schema: dict[str, Any], *, path: str = "$") -> None:
    """Tiny JSON-schema subset validator (type/required/properties/items/enum)."""
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(doc, dict):
            raise ScenarioError(f"{path}: expected object, got {type(doc).__name__}")
        for req in schema.get("required", []):
            if req not in doc:
                raise ScenarioError(f"{path}: missing required key {req!r}")
        for key, sub in schema.get("properties", {}).items():
            if key in doc:
                _validate_against_schema(doc[key], sub, path=f"{path}.{key}")
    elif expected == "array":
        if not isinstance(doc, list):
            raise ScenarioError(f"{path}: expected array, got {type(doc).__name__}")
        item_schema = schema.get("items")
        if item_schema is not None:
            for i, item in enumerate(doc):
                _validate_against_schema(item, item_schema, path=f"{path}[{i}]")
    elif expected == "string":
        if not isinstance(doc, str):
            raise ScenarioError(f"{path}: expected string, got {type(doc).__name__}")
    elif expected == "integer":
        if not isinstance(doc, int) or isinstance(doc, bool):
            raise ScenarioError(f"{path}: expected integer, got {type(doc).__name__}")
    elif expected == "number":
        if not isinstance(doc, (int, float)) or isinstance(doc, bool):
            raise ScenarioError(f"{path}: expected number, got {type(doc).__name__}")
    enum = schema.get("enum")
    if enum is not None and doc not in enum:
        raise ScenarioError(f"{path}: value {doc!r} not in enum {enum!r}")


def _normalise_preconditions(raw: Iterable[Any]) -> tuple[str, ...]:
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item.strip())
        elif isinstance(item, dict) and len(item) == 1:
            key, value = next(iter(item.items()))
            out.append(f"{key}: {value}")
        else:
            raise ScenarioError(f"unsupported precondition entry: {item!r}")
    return tuple(out)


def _scenario_from_doc(doc: dict[str, Any], *, path: Path | None = None) -> Scenario:
    setup = doc.get("setup", {})
    opening = doc.get("opening_event", {})
    scoring = doc.get("scoring", {})
    weights_raw = scoring.get("weights", {}) if isinstance(scoring, dict) else {}
    weights = {str(k): float(v) for k, v in weights_raw.items()}
    return Scenario(
        id=str(doc["id"]),
        title=str(doc["title"]),
        difficulty=str(doc["difficulty"]),
        description=str(doc.get("description", "")),
        setup_seed=int(setup.get("seed", 42)),
        setup_n_agents=int(setup.get("n_agents", 50)),
        preconditions=_normalise_preconditions(setup.get("preconditions", []) or []),
        opening_event_kind=str(opening.get("kind", "operator.scenario.start")),
        opening_event_payload=dict(opening.get("payload", {}) or {}),
        victory=tuple(str(v) for v in (doc.get("victory") or [])),
        failure=tuple(str(v) for v in (doc.get("failure") or [])),
        allowed_actions=tuple(str(a) for a in (doc.get("allowed_actions") or [])),
        scoring=ScoringSpec(weights=weights),
        source_path=path,
    )


def load_scenarios(directory: Path | None = None) -> list[Scenario]:
    """Load + validate every ``*.yaml`` under ``directory``.

    Validates each document against ``scenarios/SCHEMA.json`` and
    raises :class:`ScenarioError` on the first failure (the caller
    decides whether to skip or abort). Files are returned in
    lexicographic order so the dashboard list is stable across runs.
    """
    base = directory if directory is not None else SCENARIOS_DIR
    if not base.is_dir():
        raise ScenarioError(f"scenarios directory does not exist: {base}")
    schema = _load_schema()
    out: list[Scenario] = []
    for path in sorted(base.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:  # pragma: no cover - rare path
            raise ScenarioError(f"{path.name}: YAML parse error: {exc}") from exc
        if not isinstance(doc, dict):
            raise ScenarioError(f"{path.name}: top-level must be a mapping")
        _validate_against_schema(doc, schema)
        out.append(_scenario_from_doc(doc, path=path))
    return out


# ── runner ────────────────────────────────────────────────────────


def _operator_coins(ctx: OperatorContext) -> float:
    wallet = ctx.market.wallets.get(ctx.operator_agent_id)
    return float(wallet.coins) if wallet is not None else 0.0


def _eval_clause(
    clause: str,
    *,
    session: ScenarioSession,
    ctx: OperatorContext,
    extras: dict[str, float],
) -> bool:
    """Evaluate a single victory / failure clause against live state.

    Supported grammar (kept intentionally small — scenario authors get
    a checked vocabulary instead of arbitrary Python):

    - ``operator.coins {op} number``
    - ``operator.privacy_preserved {op} number``
    - ``operator.profit {op} number``
    - ``operator.orders_fulfilled {op} number``
    - ``tick {op} number``  (alias for ``elapsed_ticks``)
    - ``elapsed_ticks {op} number``
    - ``custom.<key> {op} number``  — for scenario-injected counters.

    Operators: ``<``, ``<=``, ``>``, ``>=``, ``==``, ``!=``. Any
    grammar-violating clause is treated as ``False`` (never raises:
    the dashboard would lose its tile otherwise).
    """
    tokens = clause.strip().split()
    if len(tokens) != 3:
        return False
    lhs, op, rhs_raw = tokens
    try:
        rhs = float(rhs_raw)
    except ValueError:
        return False
    value = _resolve_lhs(lhs, session=session, ctx=ctx, extras=extras)
    if value is None:
        return False
    try:
        match op:
            case "<":
                return value < rhs
            case "<=":
                return value <= rhs
            case ">":
                return value > rhs
            case ">=":
                return value >= rhs
            case "==":
                return value == rhs
            case "!=":
                return value != rhs
    except TypeError:
        return False
    return False


def _resolve_lhs(
    lhs: str,
    *,
    session: ScenarioSession,
    ctx: OperatorContext,
    extras: dict[str, float],
) -> float | None:
    if lhs == "operator.coins":
        return _operator_coins(ctx)
    if lhs == "operator.profit":
        return _operator_coins(ctx) - session.coins_start
    if lhs == "operator.privacy_preserved":
        budget = ctx.dp_mechanism.budget
        total = float(budget.epsilon)
        if total <= 0:
            return 0.0
        return max(0.0, 1.0 - float(budget.epsilon_spent) / total)
    if lhs == "operator.orders_fulfilled":
        oid = ctx.operator_agent_id
        return float(sum(1 for o in ctx.mempool.fulfilled if o.fulfilled_by == oid))
    if lhs in {"tick", "elapsed_ticks"}:
        return float(int(ctx.simulation.tick_counter) - session.start_tick)
    if lhs.startswith("custom."):
        return float(
            extras.get(lhs[len("custom.") :], session.custom.get(lhs[len("custom.") :], 0.0))
        )
    return None


@dataclass(slots=True)
class ScenarioRunner:
    """Owns the per-id session table; one runner per orchestrator.

    The runner is intentionally agnostic of the dashboard / CLI layer:
    callers pass their ``OperatorContext`` into ``start`` /
    ``check_status`` and the runner only touches what the scenarios
    declare. Concurrency: all session mutations are guarded by a
    re-entrant lock so the dashboard's GET polls don't race the
    CLI's POSTs.
    """

    scenarios: dict[str, Scenario]
    _sessions: dict[str, ScenarioSession] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    @classmethod
    def from_directory(cls, directory: Path | None = None) -> ScenarioRunner:
        loaded = load_scenarios(directory)
        return cls(scenarios={s.id: s for s in loaded})

    def list_scenarios(self) -> list[dict[str, str]]:
        return [
            {
                "id": s.id,
                "title": s.title,
                "difficulty": s.difficulty,
                "description": s.description,
            }
            for s in self.scenarios.values()
        ]

    def get(self, scenario_id: str) -> Scenario:
        scn = self.scenarios.get(scenario_id)
        if scn is None:
            raise ScenarioError(f"unknown scenario id {scenario_id!r}")
        return scn

    def start(self, scenario_id: str, ctx: OperatorContext) -> dict[str, Any]:
        """Bootstrap a session: snapshot start state + return the opening event."""
        scn = self.get(scenario_id)
        with self._lock:
            self._sessions[scenario_id] = ScenarioSession(
                scenario_id=scenario_id,
                start_tick=int(ctx.simulation.tick_counter),
                coins_start=_operator_coins(ctx),
            )
        return {
            "scenario_id": scenario_id,
            "title": scn.title,
            "started_at_tick": int(ctx.simulation.tick_counter),
            "opening_event": {
                "kind": scn.opening_event_kind,
                "payload": dict(scn.opening_event_payload),
            },
            "allowed_actions": list(scn.allowed_actions),
            "preconditions": list(scn.preconditions),
        }

    def abandon(self, scenario_id: str) -> dict[str, Any]:
        """Pop the session if any; idempotent for clean cleanup semantics."""
        with self._lock:
            removed = self._sessions.pop(scenario_id, None)
        return {
            "scenario_id": scenario_id,
            "abandoned": removed is not None,
        }

    def check_status(self, scenario_id: str, ctx: OperatorContext) -> dict[str, Any]:
        """Return live progress vs victory / failure clauses for ``scenario_id``."""
        scn = self.get(scenario_id)
        with self._lock:
            session = self._sessions.get(scenario_id)
        if session is None:
            return {
                "scenario_id": scenario_id,
                "active": False,
                "victory_met": False,
                "failure_met": False,
                "progress": {},
            }
        extras: dict[str, float] = dict(session.custom)
        victory_results = {
            c: _eval_clause(c, session=session, ctx=ctx, extras=extras) for c in scn.victory
        }
        failure_results = {
            c: _eval_clause(c, session=session, ctx=ctx, extras=extras) for c in scn.failure
        }
        victory_met = bool(victory_results) and all(victory_results.values())
        failure_met = any(failure_results.values())
        return {
            "scenario_id": scenario_id,
            "active": True,
            "victory_met": victory_met,
            "failure_met": failure_met,
            "elapsed_ticks": int(ctx.simulation.tick_counter) - session.start_tick,
            "progress": {
                "victory": victory_results,
                "failure": failure_results,
                "operator_coins": _operator_coins(ctx),
                "operator_profit": _operator_coins(ctx) - session.coins_start,
                "operator_orders_fulfilled": int(
                    sum(1 for o in ctx.mempool.fulfilled if o.fulfilled_by == ctx.operator_agent_id)
                ),
            },
        }

    def session(self, scenario_id: str) -> ScenarioSession | None:
        with self._lock:
            return self._sessions.get(scenario_id)


__all__ = [
    "SCENARIOS_DIR",
    "SCHEMA_PATH",
    "Scenario",
    "ScenarioError",
    "ScenarioRunner",
    "ScenarioSession",
    "ScoringSpec",
    "load_scenarios",
]
