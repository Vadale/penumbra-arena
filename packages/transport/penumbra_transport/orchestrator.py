"""Run-time orchestrator: simulation + chain together.

Concept taught: where the seams of the architecture meet. The
`Simulation` and the `Node` are independent in their packages — neither
imports the other. The orchestrator binds them together at the
`on_match_end` callback: every settled match becomes a `MatchOutcome`
transaction in the mempool, and a periodic block-production task
finalises blocks containing those outcomes.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
from dataclasses import dataclass, field

from penumbra_chain.block import MatchOutcome
from penumbra_chain.node import Node
from penumbra_core.agent import Agent
from penumbra_core.arena import Arena
from penumbra_core.match import Match
from penumbra_core.simulation import Simulation

logger = logging.getLogger(__name__)

BLOCK_INTERVAL_SECONDS_DEFAULT = 10.0


@dataclass(slots=True)
class Orchestrator:
    """Owns a Simulation + a chain Node and pumps match outcomes between them."""

    simulation: Simulation
    node: Node
    block_interval: float = BLOCK_INTERVAL_SECONDS_DEFAULT
    _block_task: asyncio.Task[None] | None = field(default=None, init=False)
    _started_at: float | None = field(default=None, init=False)
    _last_block_height: int = field(default=-1, init=False)

    @classmethod
    def build(cls, simulation: Simulation, *, n_validators: int = 4) -> Orchestrator:
        node = Node.boot(n_validators=n_validators)
        orchestrator = cls(simulation=simulation, node=node)
        simulation.on_match_end = orchestrator._on_match_end
        return orchestrator

    async def start(self) -> None:
        if self._block_task is not None and not self._block_task.done():
            return
        self._started_at = time.monotonic()
        self._block_task = asyncio.create_task(
            self._block_production_loop(), name="penumbra-block-loop"
        )

    async def stop(self) -> None:
        if self._block_task is None:
            return
        self._block_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._block_task
        self._block_task = None

    # ── internals ────────────────────────────────────────────────────

    def _on_match_end(self, match: Match, arena: Arena, _agents: list[Agent]) -> None:
        outcome = MatchOutcome(
            match_id=match.id,
            winner_agent_id=match.winner_agent_id,
            winning_goal=match.winning_goal,
            started_tick=match.started_tick,
            end_tick=match.end_tick if match.end_tick is not None else 0,
            end_reason=match.status.value,
            arena_signature=hashlib.sha256(
                f"arena-{arena.tick}-{arena.graph.number_of_edges()}".encode()
            ).digest(),
        )
        self.node.submit_outcome(outcome)

    async def _block_production_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.block_interval)
                try:
                    block = self.node.produce_block()
                except Exception:
                    logger.exception("block production raised; continuing")
                    continue
                if block is not None:
                    self._last_block_height = block.header.height
                    logger.info(
                        "produced block %d with %d outcomes",
                        block.header.height,
                        len(block.payload),
                    )
        except asyncio.CancelledError:
            raise
