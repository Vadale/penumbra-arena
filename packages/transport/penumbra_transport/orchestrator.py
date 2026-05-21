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
from penumbra_crypto.dp import DPMechanism, PrivacyBudget

from penumbra_transport.agent_signing import AgentKeystore
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
    keystore: AgentKeystore
    block_interval: float = BLOCK_INTERVAL_SECONDS_DEFAULT
    heatmap_interval: float = HEATMAP_INTERVAL_SECONDS_DEFAULT
    analytics_interval: float = ANALYTICS_INTERVAL_SECONDS_DEFAULT
    _block_task: asyncio.Task[None] | None = field(default=None, init=False)
    _heatmap_task: asyncio.Task[None] | None = field(default=None, init=False)
    _analytics_task: asyncio.Task[None] | None = field(default=None, init=False)
    _started_at: float | None = field(default=None, init=False)
    _last_block_height: int = field(default=-1, init=False)
    _last_signed_tick: int = field(default=-1, init=False)

    @classmethod
    def build(
        cls,
        simulation: Simulation,
        *,
        n_validators: int = 4,
        dp_total_epsilon: float = 5.0,
        dp_epsilon_per_release: float = 0.05,
    ) -> Orchestrator:
        node = Node.boot(n_validators=n_validators)
        # Wire a DP mechanism into the heatmap. A 5.0 ε budget at 0.05 ε
        # per release supports 100 noised releases before the accountant
        # refuses further DP-protected output (the system then logs a
        # warning and continues to release the clean aggregate).
        budget = PrivacyBudget(epsilon=dp_total_epsilon)
        dp_mechanism = DPMechanism(budget)
        heatmap = EncryptedHeatmap.for_simulation(
            get_backend(),
            simulation,
            dp_mechanism=dp_mechanism,
            dp_epsilon_per_release=dp_epsilon_per_release,
        )
        pipeline = DashboardPipeline()
        keystore = AgentKeystore.for_n_agents(len(simulation.agents))
        orchestrator = cls(
            simulation=simulation,
            node=node,
            heatmap=heatmap,
            pipeline=pipeline,
            keystore=keystore,
        )
        simulation.on_match_end = orchestrator._on_match_end
        return orchestrator

    def sign_and_verify_moves(self) -> None:
        """Sign-and-verify the current tick's agent positions.

        Runs once per heatmap iteration. The signing happens *after* the
        moves in the tick loop because the simulation owns the policy
        decision; from the orchestrator's perspective each position the
        agent is currently on IS the move it most recently made. The
        verifier (same process) checks each sig immediately — what we're
        demonstrating is the protocol shape, not adversarial separation.
        """
        tick = self.simulation.tick_counter
        if tick <= self._last_signed_tick:
            return
        self._last_signed_tick = tick
        # Snapshot agent positions BEFORE the sign+verify pass; the
        # simulation tick loop runs concurrently and can mutate
        # `agent.position` between the sign() and the verify() of the
        # same row, producing spurious rejections.
        snapshot: list[tuple[int, int]] = [
            (agent.id, agent.position) for agent in self.simulation.agents
        ]
        for agent_id, target_node in snapshot:
            sig = self.keystore.sign_move(agent_id=agent_id, tick=tick, target_node=target_node)
            self.keystore.verify_move(
                agent_id=agent_id,
                tick=tick,
                target_node=target_node,
                signature=sig,
            )

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

    def _sample_utterances(self) -> list[str]:
        """One utterance per agent, sampled from a templated corpus by action.

        The action category is derived crudely from each agent's position
        modulo 4. Pedagogically: it's enough to seed a meaningful topic
        signal — BERTopic will find the structure as long as the corpus
        has any structure at all.
        """
        from penumbra_analytics.topics import ALL_ACTIONS, utterance_for

        rng = self.simulation.seeded.numpy_for("utterances")
        out: list[str] = []
        for agent in self.simulation.agents:
            action = ALL_ACTIONS[agent.position % len(ALL_ACTIONS)]
            out.append(utterance_for(action, rng))
        return out

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
                    # Synthesise per-tick agent utterances. We map each
                    # agent's last action (encoded as the direction of
                    # its most recent hop) to one of {explore, exploit,
                    # defend, ally} and sample a templated phrase.
                    utterances = self._sample_utterances()
                    self.pipeline.observe(
                        tick=self.simulation.tick_counter,
                        positions=positions,
                        heatmap=heatmap_density,
                        utterances=utterances,
                    )
                    await asyncio.to_thread(self.pipeline.recompute)
                    # Sign + verify the current tick's moves. The protocol
                    # demo is per-tick even though analytics is per-second
                    # because the heatmap is the cadence we already pay.
                    await asyncio.to_thread(self.sign_and_verify_moves)
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
