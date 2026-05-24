"""Operator action queue.

Concept taught: a *deterministic action queue* is what turns an
interactive operator into a reproducible scenario. Every action is
stamped with the tick at which it was *submitted* and an insertion
sequence number; the simulation drains the queue at the START of the
next tick, applying actions in ``(submit_tick, sequence)`` order.

Thread safety: the CLI ``pno`` and (Tier 2) the Operator Console can
both submit concurrently while the simulation tick loop drains. A
``threading.Lock`` guards every mutation; the lock is uncontended on
the steady-state path (one drain per tick, sparse submissions).

Bounded by ``DEFAULT_MAX_QUEUE`` so a runaway client can't grow the
queue without bound; the oldest entry is dropped to make room (the
test suite asserts behaviour on the realistic <=100 entries / tick
regime so the drop path is documentation, not load-bearing).
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from penumbra_operator.actions import OperatorAction

DEFAULT_MAX_QUEUE: Final[int] = 4096


@dataclass(slots=True)
class _Entry:
    """One enqueued action with its insertion sequence number."""

    sequence: int
    action: OperatorAction


@dataclass(slots=True)
class OperatorQueue:
    """Thread-safe FIFO of pending operator actions.

    Use :meth:`submit` from any thread; call :meth:`pop_due` once per
    tick from the simulation loop to drain everything that's eligible
    for the given tick. Eligibility: ``action.target_tick is None`` or
    ``action.target_tick <= current_tick``.
    """

    max_queue: int = DEFAULT_MAX_QUEUE
    _entries: deque[_Entry] = None  # type: ignore[assignment]
    _next_sequence: int = 0
    _lock: threading.Lock = None  # type: ignore[assignment]
    _submitted: int = 0
    _dropped: int = 0

    def __post_init__(self) -> None:
        # Slotted dataclasses can't have mutable defaults in the field
        # decorator (the value would be shared across instances); we
        # build the per-instance state lazily here instead.
        self._entries = deque(maxlen=self.max_queue)
        self._lock = threading.Lock()

    def submit(self, action: OperatorAction) -> int:
        """Append ``action`` to the queue. Returns its sequence number."""
        with self._lock:
            if len(self._entries) >= self.max_queue:
                # deque(maxlen=...) silently drops the oldest entry; we
                # still count it so the dashboard can surface the loss.
                self._dropped += 1
            sequence = self._next_sequence
            self._next_sequence += 1
            self._entries.append(_Entry(sequence=sequence, action=action))
            self._submitted += 1
            return sequence

    def pop_due(self, current_tick: int) -> list[OperatorAction]:
        """Return every action eligible for ``current_tick``, in order.

        Order: ``(submit_tick, sequence)``. The simulation loop calls
        this at the START of a tick so the actions for that tick are
        applied before the agents move. Conflict resolution (e.g. two
        ``move`` actions in a row) is the handler's responsibility;
        :func:`actions.coalesce_moves` is the canonical helper.
        """
        with self._lock:
            due: list[_Entry] = []
            remaining: deque[_Entry] = deque(maxlen=self.max_queue)
            for entry in self._entries:
                target = entry.action.target_tick
                if target is None or target <= current_tick:
                    due.append(entry)
                else:
                    remaining.append(entry)
            self._entries = remaining
        due.sort(key=lambda e: (e.action.submit_tick, e.sequence))
        return [entry.action for entry in due]

    def peek(self) -> list[OperatorAction]:
        """Snapshot of currently-queued actions (for the /operator/status mirror)."""
        with self._lock:
            return [entry.action for entry in self._entries]

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def stats(self) -> dict[str, int]:
        """Lifetime + queued counters for the status endpoint."""
        with self._lock:
            return {
                "queued": len(self._entries),
                "submitted_total": self._submitted,
                "dropped_total": self._dropped,
            }

    def extend(self, actions: Iterable[OperatorAction]) -> None:
        """Bulk-submit actions; preserves call order via the sequence number."""
        for action in actions:
            self.submit(action)


__all__ = ["DEFAULT_MAX_QUEUE", "OperatorQueue"]
