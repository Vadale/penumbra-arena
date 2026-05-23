"""In-process event bus for cross-pillar reactions.

Concept taught: a tiny synchronous publisher-subscriber so the
orchestrator can route signals between pillars (analytics → logistics,
security → market, chain → economy, etc.) without each pillar growing
hard imports of the others. Handlers run inline at the analytics-tick
cadence (1 Hz); back-pressure is the analytics loop itself.

Spec: INTER_SILO_INTEGRATION_PLAN.md Tier 1.

Constraints:
- Handlers must be IDEMPOTENT — same event delivered twice should
  produce the same effect as once.
- Handlers must be SIDE-EFFECT-LOCAL — no recursive emits from inside
  a handler; if a handler wants to trigger another event, queue it via
  ``EventBus.emit_next_tick``.
- Handlers must complete < 1 ms p99; the bus records p99 latency per
  kind in ``stats()`` so regressions surface in the dashboard.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

logger = logging.getLogger(__name__)

_HISTORY_CAP: Final[int] = 1024
_LATENCY_CAP_PER_KIND: Final[int] = 256


@dataclass(frozen=True, slots=True)
class Event:
    """One immutable signal flowing through the bus."""

    kind: str  # canonical dotted name, e.g. "garch.spike"
    tick: int
    payload: dict[str, object] = field(default_factory=dict)


EventHandler = Callable[[Event], None]


@dataclass(slots=True)
class _HandlerStats:
    n_calls: int = 0
    n_errors: int = 0
    latencies_us: deque[float] = field(default_factory=lambda: deque(maxlen=_LATENCY_CAP_PER_KIND))

    def p99_us(self) -> float:
        if not self.latencies_us:
            return 0.0
        ordered = sorted(self.latencies_us)
        idx = max(0, int(0.99 * (len(ordered) - 1)))
        return float(ordered[idx])


@dataclass(slots=True)
class EventBus:
    """Sync event bus owned by the orchestrator."""

    _handlers: dict[str, list[EventHandler]] = field(default_factory=lambda: defaultdict(list))
    _history: deque[Event] = field(default_factory=lambda: deque(maxlen=_HISTORY_CAP))
    _emit_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _handler_stats: dict[str, _HandlerStats] = field(
        default_factory=lambda: defaultdict(_HandlerStats)
    )
    _next_tick_queue: list[Event] = field(default_factory=list)
    _emitting: bool = False

    def subscribe(self, kind: str, handler: EventHandler) -> None:
        """Register a handler for events of ``kind``. Re-subscribing
        the same handler is idempotent."""
        if handler not in self._handlers[kind]:
            self._handlers[kind].append(handler)

    def unsubscribe(self, kind: str, handler: EventHandler) -> None:
        if handler in self._handlers.get(kind, ()):
            self._handlers[kind].remove(handler)

    def emit(self, event: Event) -> None:
        """Dispatch ``event`` synchronously to all subscribers.

        If called from inside a handler, the event is queued for the
        NEXT bus drain instead of dispatched immediately (prevents
        recursion).
        """
        if self._emitting:
            self._next_tick_queue.append(event)
            return
        self._history.append(event)
        self._emit_counts[event.kind] += 1
        handlers = list(self._handlers.get(event.kind, ()))
        self._emitting = True
        try:
            for h in handlers:
                stats = self._handler_stats[event.kind]
                t0 = time.perf_counter_ns()
                try:
                    h(event)
                except Exception:
                    stats.n_errors += 1
                    logger.exception("event handler raised for %s", event.kind)
                stats.n_calls += 1
                stats.latencies_us.append((time.perf_counter_ns() - t0) / 1000.0)
        finally:
            self._emitting = False
        # Drain any events handlers queued for the next tick.
        if self._next_tick_queue:
            queued = self._next_tick_queue
            self._next_tick_queue = []
            for evt in queued:
                self.emit(evt)

    def emit_next_tick(self, event: Event) -> None:
        """Schedule ``event`` for the next bus drain unconditionally."""
        self._next_tick_queue.append(event)

    def recent(self, limit: int = 50) -> list[Event]:
        return list(self._history)[-limit:]

    def stats(self) -> dict[str, object]:
        """Snapshot for the /events/recent + EventBus tile endpoints."""
        return {
            "history_size": len(self._history),
            "emit_counts": dict(self._emit_counts),
            "handler_stats": {
                kind: {
                    "n_calls": s.n_calls,
                    "n_errors": s.n_errors,
                    "p99_us": s.p99_us(),
                }
                for kind, s in self._handler_stats.items()
            },
            "queued_next_tick": len(self._next_tick_queue),
        }

    def clear(self) -> None:
        """Reset for tests + orchestrator restarts."""
        self._handlers.clear()
        self._history.clear()
        self._emit_counts.clear()
        self._handler_stats.clear()
        self._next_tick_queue.clear()
        self._emitting = False
