"""Pending-transaction pool.

Concept taught: the mempool is the staging area between user submission
and inclusion in a block. In a real chain it's gossiped between nodes,
sorted by fee, and may evict stale entries. In Penumbra's single-process
node it's just an in-memory FIFO of `MatchOutcome` objects awaiting the
next block.
"""

from __future__ import annotations

from collections import deque

from penumbra_chain.block import MatchOutcome


class Mempool:
    """Bounded FIFO of pending match outcomes."""

    __slots__ = ("_queue", "capacity")

    def __init__(self, capacity: int = 1024) -> None:
        self.capacity = capacity
        self._queue: deque[MatchOutcome] = deque(maxlen=capacity)

    def submit(self, outcome: MatchOutcome) -> None:
        self._queue.append(outcome)

    def drain(self, n: int) -> tuple[MatchOutcome, ...]:
        """Pop up to `n` outcomes for inclusion in the next block."""
        taken: list[MatchOutcome] = []
        while self._queue and len(taken) < n:
            taken.append(self._queue.popleft())
        return tuple(taken)

    def __len__(self) -> int:
        return len(self._queue)

    def peek(self) -> tuple[MatchOutcome, ...]:
        """Snapshot of pending outcomes without removing them (for the explorer)."""
        return tuple(self._queue)
