"""Match — one episode of the perpetual simulation.

Concept taught: an *episode* is an artificial boundary imposed on a
continuous-time process. In Penumbra the simulation runs forever, but for
the sake of inferential statistics (Mann-Whitney across matches, etc.) and
the blockchain (one block per match) we draw boundaries. A match ends when
any agent reaches a goal node, or when the tick budget is exceeded.

Agents persist across matches; only the arena and the match metadata reset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from penumbra_core.arena import NodeId


class MatchStatus(StrEnum):
    """Lifecycle of a single match."""

    RUNNING = "running"
    WON = "won"
    EXPIRED = "expired"


@dataclass(slots=True)
class Match:
    """One episode bracket. The simulation owns the *current* match."""

    id: int
    started_at: str
    started_tick: int
    max_ticks: int = 1_200
    status: MatchStatus = MatchStatus.RUNNING
    winner_agent_id: int | None = None
    winning_goal: NodeId | None = None
    end_tick: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def start(cls, match_id: int, current_tick: int, *, max_ticks: int = 1_200) -> Match:
        return cls(
            id=match_id,
            started_at=datetime.now(UTC).isoformat(),
            started_tick=current_tick,
            max_ticks=max_ticks,
        )

    def declare_winner(self, agent_id: int, goal: NodeId, tick: int) -> None:
        self.status = MatchStatus.WON
        self.winner_agent_id = agent_id
        self.winning_goal = goal
        self.end_tick = tick

    def expire(self, tick: int) -> None:
        self.status = MatchStatus.EXPIRED
        self.end_tick = tick

    @property
    def is_over(self) -> bool:
        return self.status is not MatchStatus.RUNNING

    def ticks_elapsed(self, current_tick: int) -> int:
        return current_tick - self.started_tick
