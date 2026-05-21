"""Run-time orchestrator: simulation + chain + encrypted heatmap.

Concept taught: where the seams of the architecture meet. The
`Simulation`, the `Node`, and the `EncryptedHeatmap` are independent in
their packages — none imports any other. The orchestrator binds them
together: every settled match becomes a `MatchOutcome` transaction in
the mempool (via `on_match_end`), a periodic block-production task
finalises blocks containing those outcomes, and a separate heatmap
task encrypts the agent positions once per second and decrypts only
the aggregate density.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
from dataclasses import dataclass, field

import numpy as np

from penumbra_analytics.dashboard_pipeline import DashboardPipeline, DashboardSnapshot
from penumbra_chain.block import MatchOutcome
from penumbra_chain.node import Node
from penumbra_core.agent import Agent
from penumbra_core.arena import Arena
from penumbra_core.match import Match
from penumbra_core.simulation import Simulation
from penumbra_crypto.ckks import get_backend

from penumbra_transport.encrypted_heatmap import EncryptedHeatmap

logger = logging.getLogger(__name__)

BLOCK_INTERVAL_SECONDS_DEFAULT = 10.0
HEATMAP_INTERVAL_SECONDS_DEFAULT = 1.0
ANALYTICS_INTERVAL_SECONDS_DEFAULT = 1.0


@dataclass(slots=True)
class Orchestrator:
    """Owns Simulation + chain Node + encrypted heatmap + analytics pipeline."""

    simulation: Simulation
    node: Node
    heatmap: EncryptedHeatmap
    pipeline: DashboardPipeline
    block_interval: float = BLOCK_INTERVAL_SECONDS_DEFAULT
    heatmap_interval: float = HEATMAP_INTERVAL_SECONDS_DEFAULT
    analytics_interval: float = ANALYTICS_INTERVAL_SECONDS_DEFAULT
    _block_task: asyncio.Task[None] | None = field(default=None, init=False)
    _heatmap_task: asyncio.Task[None] | None = field(default=None, init=False)
    _analytics_task: asyncio.Task[None] | None = field(default=None, init=False)
    _started_at: float | None = field(default=None, init=False)
    _last_block_height: int = field(default=-1, init=False)

    @classmethod
    def build(cls, simulation: Simulation, *, n_validators: int = 4) -> Orchestrator:
        node = Node.boot(n_validators=n_validators)
        heatmap = EncryptedHeatmap.for_simulation(get_backend(), simulation)
        pipeline = DashboardPipeline()
        orchestrator = cls(
            simulation=simulation, node=node, heatmap=heatmap, pipeline=pipeline
        )
        simulation.on_match_end = orchestrator._on_match_end
        return orchestrator

    @property
    def latest_dashboard_snapshot(self) -> DashboardSnapshot:
        return self.pipeline.snapshot

    async def start(self) -> None:
        if self._block_task is not None and not self._block_task.done():
            return
        self._started_at = time.monotonic()
        self._block_task = asyncio.create_task(
            self._block_production_loop(), name="penumbra-block-loop"
        )
        self._heatmap_task = asyncio.create_task(self._heatmap_loop(), name="penumbra-heatmap-loop")
        self._analytics_task = asyncio.create_task(
            self._analytics_loop(), name="penumbra-analytics-loop"
        )

    async def stop(self) -> None:
        for attr in ("_block_task", "_heatmap_task", "_analytics_task"):
            task = getattr(self, attr)
            if task is None:
                continue
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            setattr(self, attr, None)

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

    async def _heatmap_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.heatmap_interval)
                try:
                    await asyncio.to_thread(self.heatmap.compute, self.simulation)
                except Exception:
                    logger.exception("encrypted-heatmap compute raised; continuing")
        except asyncio.CancelledError:
            raise

    async def _analytics_loop(self) -> None:
        """Feed the dashboard pipeline at 1 Hz and re-run any due consumer."""
        try:
            while True:
                await asyncio.sleep(self.analytics_interval)
                try:
                    positions = np.asarray(
                        [a.position for a in self.simulation.agents], dtype=np.float64
                    )
                    heatmap_density = (
                        self.heatmap.latest.density if self.heatmap.latest is not None else None
                    )
                    self.pipeline.observe(
                        tick=self.simulation.tick_counter,
                        positions=positions,
                        heatmap=heatmap_density,
                    )
                    await asyncio.to_thread(self.pipeline.recompute)
                except Exception:
                    logger.exception("analytics pipeline raised; continuing")
        except asyncio.CancelledError:
            raise

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
