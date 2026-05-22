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
# Stress-test fix: TenSEAL CKKS encrypt+sum+decrypt costs ~12 MB/sec
# of C++ allocation at 1 Hz, and the C-extension allocator doesn't
# release it cleanly. Sliding to 5 s cuts the leak 5x without
# meaningfully changing the UX — the heatmap visual updates every
# few seconds, not every tick. Override via env var if you want
# faster sampling for a particular demo.
HEATMAP_INTERVAL_SECONDS_DEFAULT = 5.0
ANALYTICS_INTERVAL_SECONDS_DEFAULT = 1.0


def _release_torch_caches() -> None:
    """Best-effort flush of torch's MPS/CUDA/CPU allocator caches.

    Stress-test fix: per-tick MAPPO actor calls allocate temporary
    MPS tensors that torch's cache holds for re-use. Over a long run
    those caches climb to multi-GB. Periodic empty_cache reclaims the
    backing memory without affecting model weights.
    """
    try:
        import torch  # pyright: ignore[reportMissingImports]
    except ImportError:
        return
    if hasattr(torch, "mps") and torch.backends.mps.is_available():
        with contextlib.suppress(Exception):
            torch.mps.empty_cache()
    if torch.cuda.is_available():
        with contextlib.suppress(Exception):
            torch.cuda.empty_cache()


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
    purchase_clock: object | None = field(default=None, init=False)

    @classmethod
    def build(
        cls,
        simulation: Simulation,
        *,
        n_validators: int = 4,
        dp_total_epsilon: float = 1000.0,
        dp_epsilon_per_release: float = 0.01,
    ) -> Orchestrator:
        node = Node.boot(n_validators=n_validators)
        # Wire a DP mechanism into the heatmap. Defaults (post stress-
        # test tuning): ε_total=1000.0 / per-release=0.01 supports
        # ~100,000 noised releases at the 1 Hz cadence — about 27 hours
        # before the accountant trips. Earlier defaults (5.0 / 0.05)
        # exhausted the budget in ~50 seconds, which made the live
        # demo log "DP off" almost immediately. Picking a longer
        # horizon makes the DP claim observable across a real session.
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
        # Build city inventories from the arena's nodes + simulation
        # seed so the assortment is deterministic per world.
        from penumbra_core.economy import PurchaseClock, city_inventories

        inventories = city_inventories(
            nodes=list(simulation.arena.graph.nodes()),
            seed=int(simulation.seeded.master),
        )
        orchestrator.purchase_clock = PurchaseClock(inventories=inventories)
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

        Returns [] if PENUMBRA_ENABLE_TOPICS != "1". The BERTopic
        consumer is the heaviest tick-time cost (stress test measured
        4.7 Hz vs 10 Hz target with topics on; closer to 9 Hz with
        topics off). Default-off keeps the simulation responsive;
        the user opts in to spend tick budget on topic modelling.
        """
        import os

        if os.environ.get("PENUMBRA_ENABLE_TOPICS") != "1":
            return []
        from penumbra_analytics.topics import ALL_ACTIONS, utterance_for

        rng = self.simulation.seeded.numpy_for("utterances")
        out: list[str] = []
        for agent in self.simulation.agents:
            action = ALL_ACTIONS[agent.position % len(ALL_ACTIONS)]
            out.append(utterance_for(action, rng))
        return out

    async def _heatmap_loop(self) -> None:
        import gc

        iterations = 0
        try:
            while True:
                await asyncio.sleep(self.heatmap_interval)
                try:
                    await asyncio.to_thread(self.heatmap.compute, self.simulation)
                except Exception:
                    logger.exception("encrypted-heatmap compute raised; continuing")
                iterations += 1
                # Stress-test fix: CKKS + torch MPS allocate
                # C-extension memory that Python's GC doesn't sweep on
                # its normal generation cadence. gc.collect every 10s +
                # torch.mps.empty_cache every 30s caps the residue.
                if iterations % 10 == 0:
                    gc.collect()
                if iterations % 30 == 0:
                    _release_torch_caches()
        except asyncio.CancelledError:
            raise

    async def _analytics_loop(self) -> None:
        """Feed the dashboard pipeline at 1 Hz and re-run any due consumer."""
        import gc

        iterations = 0
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
                    # Settle city-arrival purchases for this tick.
                    if self.purchase_clock is not None:
                        agent_positions = {a.id: a.position for a in self.simulation.agents}
                        rng = self.simulation.seeded.numpy_for("economy")
                        events = self.purchase_clock.settle_tick(  # type: ignore[attr-defined]
                            tick=self.simulation.tick_counter,
                            agent_positions=agent_positions,
                            rng=rng,
                        )
                        if events:
                            self.pipeline.record_purchases(events)
                    await asyncio.to_thread(self.pipeline.recompute)
                    # Sign + verify the current tick's moves. The protocol
                    # demo is per-tick even though analytics is per-second
                    # because the heatmap is the cadence we already pay.
                    await asyncio.to_thread(self.sign_and_verify_moves)
                except Exception:
                    logger.exception("analytics pipeline raised; continuing")
                iterations += 1
                # Stress-test fix: pqcrypto Dilithium sign+verify + numpy
                # buffers from the consumers (ripser, scipy, numpyro)
                # accumulate temporaries that Python's normal GC sweeps
                # too lazily. Full-collect every 10s caps the working set.
                if iterations % 10 == 0:
                    gc.collect()
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
