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
from collections import deque
from dataclasses import dataclass, field

import numpy as np
from penumbra_analytics.dashboard_pipeline import DashboardPipeline, DashboardSnapshot
from penumbra_chain.block import MatchOutcome
from penumbra_chain.node import Node
from penumbra_core.agent import Agent
from penumbra_core.arena import Arena
from penumbra_core.logistics import (
    CargoConstraints,
    DemandModel,
    LogisticsMempool,
    ReorderPolicy,
    assign_carriers,
)
from penumbra_core.logistics_echelon import EchelonNetwork
from penumbra_core.logistics_echelon import step as _echelon_step
from penumbra_core.logistics_or import (
    VRPInstance,
    VRPOrder,
    VRPSolution,
    build_arena_distance_matrix,
    solve_greedy_nearest_neighbor,
    solve_two_opt,
)
from penumbra_core.match import Match
from penumbra_core.simulation import Simulation
from penumbra_crypto.ckks import get_backend
from penumbra_crypto.dp import DPMechanism, PrivacyBudget

from penumbra_transport.agent_signing import AgentKeystore
from penumbra_transport.encrypted_heatmap import EncryptedHeatmap
from penumbra_transport.events import Event, EventBus

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


def _is_finite(value: float) -> bool:
    """math.isfinite shim that avoids the extra import at call sites."""
    import math

    return math.isfinite(value)


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
    market: object | None = field(default=None, init=False)
    event_bus: EventBus = field(default_factory=EventBus, init=False)
    cargo: CargoConstraints | None = field(default=None, init=False)
    demand: DemandModel | None = field(default=None, init=False)
    reorder_policy: ReorderPolicy | None = field(default=None, init=False)
    logistics_mempool: LogisticsMempool | None = field(default=None, init=False)
    echelon_network: EchelonNetwork | None = field(default=None, init=False)
    federated_trainer: object | None = field(default=None, init=False)
    _logistics_lead_time_ticks: int = field(default=5, init=False)
    _logistics_iteration: int = field(default=0, init=False)
    # Phase 6a Tier 4 — EMA of MAPPO mean_reward across PPO iterations
    # + rolling history of policy.improved events (surfaced by the
    # /events/policy-improvements endpoint).
    _policy_reward_baseline: float | None = field(default=None, init=False)
    # Bounded ring (oldest evicted automatically) — the /events/policy
    # -improvements endpoint reads the last N entries via list(...).
    _policy_improvements: deque[Event] = field(
        default_factory=lambda: deque(maxlen=256), init=False
    )
    # Tier 2 — agent_id → until_tick for an active security block. The
    # orchestrator scans this dict each analytics tick and calls
    # ``unblock_agent`` once ``current_tick >= until_tick``.
    _pending_unblocks: dict[int, int] = field(default_factory=dict, init=False)
    _blocked_history_count: int = field(default=0, init=False)
    # Phase 6b Tier 1 — operator slot. Lazy-built on first
    # /operator/enable. operator_queue is the FIFO the API endpoints
    # push into; the simulation's pre_tick_hook drains it. recent_results
    # is a small rolling window for the /operator/status endpoint.
    operator: object | None = field(default=None, init=False)
    operator_context: object | None = field(default=None, init=False)
    operator_queue: object | None = field(default=None, init=False)
    operator_recent_results: deque[object] = field(
        default_factory=lambda: deque(maxlen=200), init=False
    )
    operator_initial_coins: float = field(default=100.0, init=False)
    operator_attacks_survived: int = field(default=0, init=False)
    operator_chain_contribution: int = field(default=0, init=False)
    # Phase 6b Tier 6 — session replay. operator_session_logger is the
    # parquet-backed writer; operator_session_id is the id of the
    # currently-open session (None when operator is disabled).
    operator_session_logger: object | None = field(default=None, init=False)
    operator_session_id: str | None = field(default=None, init=False)

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
        # Build the live market: per-agent wallets, per-city inventory +
        # treasury + dynamic ask prices, production rates. The orchestrator
        # drives one Market.tick per analytics tick (sell + buy events
        # produce a Trade stream the pipeline records).
        from penumbra_core.economy import Market

        orchestrator.market = Market.build(
            nodes=list(simulation.arena.graph.nodes()),
            n_agents=len(simulation.agents),
            seed=int(simulation.seeded.master),
        )
        # Logistics layer: per-agent cargo cap, per-city demand,
        # (s, S) reorder policy + an in-memory order book. The cargo
        # attribute is attached directly to the market so the BUY
        # path enforces capacity.
        cargo = CargoConstraints.uniform(n_agents=len(simulation.agents))
        orchestrator.cargo = cargo
        orchestrator.market.cargo = cargo  # type: ignore[attr-defined]
        orchestrator.demand = DemandModel.uniform(orchestrator.market)
        orchestrator.reorder_policy = ReorderPolicy.fractional(orchestrator.market)
        orchestrator.logistics_mempool = LogisticsMempool()
        # Phase 6a Tier 1 — wire analytics→cross-pillar events.
        orchestrator._wire_event_bus()
        return orchestrator

    def _wire_event_bus(self) -> None:
        """Connect pipeline + DP-mechanism signals; register Tier 1 + Tier 3 handlers."""
        bus = self.event_bus

        # Pipeline emits via this hook; orchestrator forwards to the bus.
        def _forward(kind: str, payload: dict[str, object]) -> None:
            bus.emit(Event(kind=kind, tick=self.simulation.tick_counter, payload=payload))

        self.pipeline.on_signal = _forward  # type: ignore[attr-defined]

        # Phase 6a Tier 3 — wire the heatmap's DP mechanism's signal
        # hook into the same bus. NON-CRYPTOGRAPHIC: only signal
        # emission, no change to noise math or accounting.
        dp_mechanism = self.heatmap.dp_mechanism
        if dp_mechanism is not None:

            def _dp_forward(kind: str, payload: dict[str, float]) -> None:
                bus.emit(
                    Event(
                        kind=kind,
                        tick=self.simulation.tick_counter,
                        payload=dict(payload),
                    )
                )

            dp_mechanism.on_signal = _dp_forward

        # Tier 1 handlers — Stats ↔ Logistics/Market.
        def on_garch_spike(event: Event) -> None:
            raw = event.payload.get("ratio", 1.0)
            ratio = float(raw if isinstance(raw, int | float) else 1.0) - 1.0
            if self.reorder_policy is not None:
                self.reorder_policy.react_to_volatility(
                    sigma_signal=ratio, current_tick=event.tick, decay_ticks=60
                )
            if self.market is not None:
                self.market.set_pricing_regime(  # type: ignore[attr-defined]
                    "volatile", ticks_active=30, current_tick=event.tick
                )

        def on_cpi_shock(event: Event) -> None:
            if self.market is not None:
                self.market.set_pricing_regime(  # type: ignore[attr-defined]
                    "crisis", ticks_active=60, current_tick=event.tick
                )

        # Tier 3 handlers — DP-budget pressure cascades to analytics
        # cadence + federated trainer gate.
        def on_dp_budget_warning(_event: Event) -> None:
            self.pipeline.degrade_for_dp_warning()

        def on_dp_budget_exhausted(_event: Event) -> None:
            self.pipeline.enter_dp_fallback()
            trainer = self.federated_trainer
            if trainer is not None and hasattr(trainer, "block_dp"):
                trainer.block_dp()  # type: ignore[attr-defined]

        bus.subscribe("garch.spike", on_garch_spike)
        bus.subscribe("cpi.shock", on_cpi_shock)
        bus.subscribe("dp.budget.warning", on_dp_budget_warning)
        bus.subscribe("dp.budget.exhausted", on_dp_budget_exhausted)

        # Tier 2 — Security ↔ Market/Logistics/FL. The keystore detects
        # rejection-threshold crossings and invokes ``on_agent_blocked``
        # to emit an ``agent.blocked`` event; the handler below propagates
        # the block to Market.blocked_agents, queues an auto-unblock at
        # ``until_tick``, and (if present) blocks the FL trainer too.
        def _keystore_emit_blocked(agent_id: int, until_tick: int) -> None:
            bus.emit(
                Event(
                    kind="agent.blocked",
                    tick=self.simulation.tick_counter,
                    payload={
                        "agent_id": int(agent_id),
                        "reason": "signing_rejected",
                        "until_tick": int(until_tick),
                    },
                )
            )

        self.keystore.on_agent_blocked = _keystore_emit_blocked

        def on_agent_blocked(event: Event) -> None:
            payload = event.payload
            agent_id_raw = payload.get("agent_id")
            until_tick_raw = payload.get("until_tick")
            if not isinstance(agent_id_raw, int) or not isinstance(until_tick_raw, int):
                return
            agent_id = int(agent_id_raw)
            until_tick = int(until_tick_raw)
            if self.market is not None:
                self.market.block_agent(agent_id)  # type: ignore[attr-defined]
            self._pending_unblocks[agent_id] = until_tick
            self._blocked_history_count += 1
            trainer = self.federated_trainer
            if trainer is not None and hasattr(trainer, "block_agent"):
                try:
                    trainer.block_agent(agent_id)  # type: ignore[attr-defined]
                except Exception:
                    logger.exception("FederatedTrainer.block_agent raised; continuing")

        bus.subscribe("agent.blocked", on_agent_blocked)

        # Tier 5 — chain emits via on_signal; orchestrator forwards to the
        # bus. The chain package has no import dependency on transport,
        # so we install the hook here.
        def _forward_chain(kind: str, payload: dict[str, object]) -> None:
            bus.emit(Event(kind=kind, tick=self.simulation.tick_counter, payload=payload))

        self.node.on_signal = _forward_chain

        # Tier 5 — chain.block.finalised → economic reward to winners.
        def on_block_finalised(event: Event) -> None:
            if self.market is None:
                return
            winners_raw = event.payload.get("winners", [])
            if not isinstance(winners_raw, list):
                return
            winners = [int(w) for w in winners_raw if isinstance(w, int)]
            self.market.credit_block_winners(winners)  # type: ignore[attr-defined]

        # Tier 5 — chain.validator.slashed → FL trainer excises the
        # slashed validator's delta (re-uses Tier 2's block_agent API).
        # Guarded with hasattr so the hook degrades gracefully if Tier 2
        # hasn't shipped block_agent on FederatedTrainer yet.
        def on_validator_slashed(event: Event) -> None:
            trainer = self.federated_trainer
            if trainer is None:
                return
            validator_id = event.payload.get("validator_id")
            if not isinstance(validator_id, int):
                return
            if hasattr(trainer, "block_agent"):
                try:
                    trainer.block_agent(validator_id)  # type: ignore[attr-defined]
                except Exception:
                    logger.exception("FederatedTrainer.block_agent raised; continuing")

        bus.subscribe("chain.block.finalised", on_block_finalised)
        bus.subscribe("chain.validator.slashed", on_validator_slashed)

        # Phase 6a Tier 4 — ML/RL ↔ Logistics convergence signal.
        # Track an EMA baseline of mean_reward across PPO iters; emit a
        # downstream policy.improved event when the latest mean_reward
        # exceeds 1.5x the baseline. The Bench leaderboard tile
        # surfaces these as "live training is converging".
        ema_alpha = 0.2
        improvement_ratio = 1.5

        def on_policy_updated(event: Event) -> None:
            raw_reward = event.payload.get("mean_reward")
            if not isinstance(raw_reward, int | float):
                return
            mean_reward = float(raw_reward)
            baseline = self._policy_reward_baseline
            if baseline is None or not _is_finite(baseline):
                self._policy_reward_baseline = mean_reward
                return
            # Trigger only when baseline is meaningfully non-zero; the
            # 1.5x ratio is meaningless against a 0 baseline.
            if abs(baseline) > 1e-6 and mean_reward > improvement_ratio * baseline:
                improved = Event(
                    kind="policy.improved",
                    tick=event.tick,
                    payload={
                        "iteration": event.payload.get("iteration"),
                        "mean_reward": mean_reward,
                        "baseline": float(baseline),
                        "ratio": float(mean_reward / baseline),
                    },
                )
                # deque(maxlen=256) evicts oldest automatically — no
                # cap-check needed. The event bus also keeps a 1024-event
                # ring so anything older stays recoverable from there.
                self._policy_improvements.append(improved)
                bus.emit(improved)
            # Update EMA AFTER the comparison so the spike isn't
            # immediately absorbed.
            self._policy_reward_baseline = ema_alpha * mean_reward + (1.0 - ema_alpha) * baseline

        bus.subscribe("ml.policy.updated", on_policy_updated)

    def _cpu_bound_analytics(self) -> None:
        """Combined recompute + sign/verify call.

        Exists so the analytics loop can hand off both CPU-bound steps
        to a single thread (one event-loop hop instead of two) without
        allocating a fresh closure per tick.
        """
        self.pipeline.recompute()
        self.sign_and_verify_moves()

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
        # Feed the survival consumer: duration in ticks, observed=True
        # iff the match ended because a winner was found.
        duration = max(1, outcome.end_tick - outcome.started_tick)
        observed = match.status.value == "won"
        self.pipeline.record_match_outcome(duration, observed)

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
                # Post-Phase-8 stress test (2026-05-23) showed RSS
                # climbing ~435 MB/h despite the previous gc.collect /
                # empty_cache cadence. The Phase 8 additions (live
                # MAPPO inference + LiveTrainer + extra crypto demo
                # endpoints) increased C-extension allocation
                # pressure. Tightened cadences below.
                if iterations % 2 == 0:  # every 10s (heatmap is 5s)
                    gc.collect()
                if iterations % 6 == 0:  # every 30s
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
                    # Iterate `self.simulation.agents` ONCE per analytics
                    # tick; both the positions ndarray and the per-id
                    # position dict reuse the same snapshot. Saves a
                    # second O(N) traversal and a transient list at 1 Hz.
                    agent_snapshot = list(self.simulation.agents)
                    positions = np.asarray([a.position for a in agent_snapshot], dtype=np.float64)
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
                    # Drive one market tick: production + price update +
                    # settle sells & buys for any agent that just moved.
                    if self.market is not None:
                        agent_positions = {a.id: a.position for a in agent_snapshot}
                        rng = self.simulation.seeded.numpy_for("economy")
                        trades = self.market.tick(  # type: ignore[attr-defined]
                            tick=self.simulation.tick_counter,
                            agent_positions=agent_positions,
                            rng=rng,
                        )
                        # Tier 1 — let market + reorder policy decay
                        # their event-driven regime modifiers before
                        # this tick's logistics step.
                        if self.market is not None:
                            self.market.tick_pricing(  # type: ignore[attr-defined]
                                self.simulation.tick_counter
                            )
                        if self.reorder_policy is not None:
                            self.reorder_policy.tick(self.simulation.tick_counter)
                        self._step_logistics()
                        self._maybe_ingest_federated()
                        self._maybe_step_federated()
                        # Stream every Trade into the pipeline; the legacy
                        # record_purchases consumer reads the buy side too.
                        self.pipeline.record_trades(  # type: ignore[attr-defined]
                            trades=trades,
                            money_supply=self.market.money_supply(),  # type: ignore[attr-defined]
                            price_index=self.market.price_index(),  # type: ignore[attr-defined]
                            wealth=self.market.wealth_distribution(),  # type: ignore[attr-defined]
                            tick=self.simulation.tick_counter,
                        )
                    # Batch the two CPU-bound steps into one thread hop
                    # so we pay only one event-loop context switch per
                    # analytics tick. Sign+verify of the tick's moves
                    # shares the heatmap's wall-clock budget; recompute
                    # runs the consumer ladder at their per-consumer
                    # cadences.
                    await asyncio.to_thread(self._cpu_bound_analytics)
                except Exception:
                    logger.exception("analytics pipeline raised; continuing")
                iterations += 1
                # Tightened post-Phase-2.5 (2026-05-23): the analytics
                # loop now also drives logistics (demand + reorder +
                # carrier dispatch + fulfilment) + multi-echelon step +
                # FL ingest/step, on top of the original market + MAPPO
                # + pipeline.recompute work. The extra per-tick allocations
                # required a tighter gc cadence to keep RSS bounded.
                # Pre-tightening clean stress showed +3019 MB/h drift;
                # post-tightening targets < 100 MB/h.
                if iterations % 2 == 0:  # every 2s
                    gc.collect()
                if iterations % 20 == 0:  # every 20s
                    _release_torch_caches()
        except asyncio.CancelledError:
            raise

    def _maybe_ingest_federated(self) -> None:
        """Append (obs, greedy-label) for every agent to the FL trainer.

        Called once per analytics tick when the federated trainer is
        enabled. Each LocalActor's buffer fills with this agent's own
        observations + the greedy-nearest-goal heuristic label, so the
        per-actor SGD path has REAL per-agent data (not synthetic
        noise).
        """
        trainer = self.federated_trainer
        if trainer is None or not getattr(trainer, "enabled", False):
            return
        try:
            from penumbra_learning.env import (
                NEIGHBOURS_K,
                OBS_PER_NEIGHBOUR,
                PAD_VALUE,
            )
        except Exception:
            return
        arena = self.simulation.arena
        goals = set(arena.goals)
        tick = self.simulation.tick_counter
        for agent in self.simulation.agents:
            obs = agent.observe(arena, tick=tick)
            neighbours = sorted(obs.neighbour_costs.keys())
            feats: list[float] = []
            best_idx = NEIGHBOURS_K  # default: stay
            best_cost = float("inf")
            for j in range(NEIGHBOURS_K):
                if j < len(neighbours):
                    n = neighbours[j]
                    cost = float(obs.neighbour_costs[n])
                    is_goal = 1.0 if n in goals else 0.0
                    feats.extend([cost, is_goal, is_goal])
                    if is_goal > 0.5 and cost < best_cost:
                        best_cost = cost
                        best_idx = j
                else:
                    feats.extend([PAD_VALUE] * OBS_PER_NEIGHBOUR)
            if best_idx == NEIGHBOURS_K and neighbours:
                # No goal among neighbours: greedy fallback = cheapest hop.
                costs = [float(obs.neighbour_costs[n]) for n in neighbours[:NEIGHBOURS_K]]
                best_idx = int(np.argmin(costs)) if costs else NEIGHBOURS_K
            obs_arr = np.asarray(feats, dtype=np.float32)
            try:
                trainer.ingest(agent.id, obs_arr, int(best_idx))  # type: ignore[attr-defined]
            except Exception:
                logger.exception("federated ingest raised; continuing")

    def _maybe_step_federated(self) -> None:
        """Run one FL round every 30 analytics ticks if the trainer is enabled.

        The cadence is intentionally coarse: each round runs `local_steps`
        synthetic SGD passes per actor, then aggregates. 30s between rounds
        keeps the analytics tick from being dominated by FL work while
        still producing visible round-by-round movement on the dashboard.
        """
        trainer = self.federated_trainer
        if trainer is None:
            return
        if not getattr(trainer, "enabled", False):
            return
        if self.simulation.tick_counter % 30 != 0:
            return
        try:
            trainer.step()  # type: ignore[attr-defined]
        except Exception:
            logger.exception("federated step raised; continuing")

    def compute_vrp_baseline(
        self,
        *,
        solver: str = "two_opt",
        max_orders: int = 32,
    ) -> VRPSolution | None:
        """Solve a snapshot VRP over the current pending orders + agent positions.

        Read-only: never mutates orchestrator / market / mempool state. The
        agent positions snapshot comes from `simulation.agents`, the
        cargo caps from `self.cargo`, the orders from `self.logistics_mempool`,
        and the distance matrix from arena shortest paths.

        Returns None if the simulation isn't ready (no mempool / no cargo).
        Caps `max_orders` to keep the inner 2-opt loop tractable on
        the M4 budget (~500 ms for 32 orders / 50 nodes / 50 agents).
        """
        if self.logistics_mempool is None or self.cargo is None or self.market is None:
            return None
        pending = self.logistics_mempool.pending[:max_orders]
        if not pending:
            return None
        distance_matrix, node_order = build_arena_distance_matrix(self.simulation.arena)
        node_idx = {n: i for i, n in enumerate(node_order)}
        orders = tuple(
            VRPOrder(
                order_id=o.id,
                node=node_idx[o.city],
                quantity=int(o.quantity),
                reward=float(o.reward),
            )
            for o in pending
            if o.city in node_idx
        )
        if not orders:
            return None
        agents = self.simulation.agents
        agent_start: list[int] = []
        agent_capacity: list[int] = []
        for agent in agents:
            if agent.position not in node_idx:
                continue
            agent_start.append(node_idx[agent.position])
            agent_capacity.append(int(self.cargo.capacity.get(agent.id, 20)))
        if not agent_start:
            return None
        instance = VRPInstance(
            n_nodes=len(node_order),
            distance_matrix=distance_matrix,
            orders=orders,
            agent_start=tuple(agent_start),
            agent_capacity=tuple(agent_capacity),
        )
        if solver == "greedy":
            return solve_greedy_nearest_neighbor(instance)
        if solver == "or_tools":
            from penumbra_core.logistics_or import solve_or_tools

            return solve_or_tools(instance)
        return solve_two_opt(instance)

    def _step_logistics(self) -> None:
        """Logistics step: demand + reorder + dispatch + agent-driven fulfilment.

        Called once per analytics tick (1 Hz). Drives:
          1. ``DemandModel.step`` — depletes city inventories, records backlog.
          2. ``ReorderPolicy.evaluate`` — places orders when below s.
          3. ``assign_carriers`` — greedy nearest-agent dispatch for any
             order without ``assigned_to``.
          4. Per-order fulfilment: if the assigned agent is at the order
             city AND its wallet has at least ``quantity`` units of the
             product, hand the goods off (city inventory ++, agent
             inventory --, ``wallet.coins`` += reward).
          5. Stale-assignment release: an order assigned for more than
             3x lead time without delivery is released back to the
             unassigned pool so the dispatcher can re-pick on the next
             tick.
          6. Phantom-carrier safety: an order that has waited more than
             5x lead time (no progress at all) is auto-fulfilled with
             ``agent_id=-1`` so the simulation never deadlocks when
             every agent is idle.
        """
        if (
            self.market is None
            or self.demand is None
            or self.reorder_policy is None
            or self.logistics_mempool is None
            or self.cargo is None
        ):
            return
        tick = self.simulation.tick_counter
        # Tier 2 — drain any expired security cool-offs BEFORE dispatch
        # so a freshly-unblocked agent can be picked this very tick.
        self._drain_pending_unblocks(tick)
        self.demand.step(self.market)
        self.reorder_policy.evaluate(market=self.market, mempool=self.logistics_mempool, tick=tick)
        agent_positions = {a.id: a.position for a in self.simulation.agents}
        assign_carriers(
            mempool=self.logistics_mempool,
            market=self.market,
            arena=self.simulation.arena,
            agent_positions=agent_positions,
            cargo=self.cargo,
            tick=tick,
            blocked_agents=self.market.blocked_agents,  # type: ignore[attr-defined]
        )
        lead = self._logistics_lead_time_ticks
        stale_threshold = max(1, 3 * lead)
        phantom_threshold = max(1, 5 * lead)
        # Snapshot first: `fulfil` mutates `pending` so iterating in
        # place would skip neighbours.
        for order in list(self.logistics_mempool.pending):
            ms = self.market.markets.get(order.city)  # type: ignore[attr-defined]
            if ms is None:
                continue
            age = tick - order.placed_tick
            carrier = order.assigned_to
            if carrier is not None:
                wallet = self.market.wallets.get(carrier)  # type: ignore[attr-defined]
                agent_pos = agent_positions.get(carrier)
                if (
                    wallet is not None
                    and agent_pos == order.city
                    and wallet.inventory.get(order.product, 0) >= order.quantity
                ):
                    wallet.inventory[order.product] -= order.quantity
                    if wallet.inventory[order.product] == 0:
                        del wallet.inventory[order.product]
                    ms.inventory[order.product] = min(
                        ms.max_inventory,
                        ms.inventory.get(order.product, 0) + order.quantity,
                    )
                    wallet.coins += order.reward
                    self.logistics_mempool.fulfil(order_id=order.id, agent_id=carrier, tick=tick)
                    continue
                assigned_age = (
                    tick - order.assigned_tick if order.assigned_tick is not None else age
                )
                if assigned_age >= stale_threshold:
                    order.assigned_to = None
                    order.assigned_tick = None
            if age >= phantom_threshold:
                ms.inventory[order.product] = min(
                    ms.max_inventory,
                    ms.inventory.get(order.product, 0) + order.quantity,
                )
                self.logistics_mempool.fulfil(order_id=order.id, agent_id=-1, tick=tick)
        self._step_echelon_network()
        self._logistics_iteration += 1

    def _drain_pending_unblocks(self, current_tick: int) -> None:
        """Tier 2 — clear expired security blocks from Market + FL trainer.

        Walks ``_pending_unblocks``; for every entry whose ``until_tick``
        is in the past, the agent is unblocked on the Market and (if a
        FederatedTrainer is attached) on the trainer too. The keystore's
        own block bookkeeping is left untouched — the cool-off there
        simply prevents redundant emits, which is fine.
        """
        if not self._pending_unblocks:
            return
        expired = [
            agent_id
            for agent_id, until_tick in self._pending_unblocks.items()
            if current_tick >= until_tick
        ]
        for agent_id in expired:
            del self._pending_unblocks[agent_id]
            if self.market is not None:
                self.market.unblock_agent(agent_id)  # type: ignore[attr-defined]
            trainer = self.federated_trainer
            if trainer is not None and hasattr(trainer, "unblock_agent"):
                try:
                    trainer.unblock_agent(agent_id)  # type: ignore[attr-defined]
                except Exception:
                    logger.exception("FederatedTrainer.unblock_agent raised; continuing")

    def _step_echelon_network(self) -> None:
        """Tier 3: advance the multi-echelon supply chain by one tick.

        Lazy-builds an `EchelonNetwork` from the current arena nodes on
        first call (20% suppliers / 30% distributors / rest cities).
        End-customer demand is sampled from the city-tier nodes at a
        small fixed rate so the bullwhip metric has a signal to
        amplify. The network is independent of `Market` / `Mempool` —
        it carries its own inventory and order book.
        """
        if self.market is None:
            return
        if self.echelon_network is None:
            try:
                self.echelon_network = EchelonNetwork.build(
                    node_ids=list(self.simulation.arena.graph.nodes()),
                    supplier_fraction=0.2,
                    distributor_fraction=0.3,
                    products=(0,),
                    lead_time=3,
                )
            except Exception:
                logger.exception("echelon network build failed; disabling Tier 3")
                self.echelon_network = None
                return
        net = self.echelon_network
        if net is None:
            return
        cities = net.nodes_by_role("city")
        if not cities:
            return
        # Constant-rate demand at every city for product 0. A heavier
        # / noisier driver would amplify the bullwhip signal but
        # 2 units/tick already exercises the (s,S) loop end-to-end.
        demand = {(c.id, 0): 2 for c in cities}
        try:
            _echelon_step(net, demand)
        except Exception:
            logger.exception("echelon step raised; continuing")

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

    # ── Phase 6b Tier 1 — operator slot lifecycle ─────────────────

    def enable_operator(self) -> dict[str, object]:
        """Bootstrap (or refresh) the operator slot.

        Idempotent: a re-enable refreshes the wallet to its initial
        state but reuses the existing keypair so signatures stay
        verifiable across the lifecycle. Returns a small dict with the
        operator id + current position, used by the /operator/enable
        endpoint response.
        """
        from penumbra_core.agent import Agent, random_walk_policy
        from penumbra_crypto.pq import sig_keygen
        from penumbra_operator.actions import OperatorContext, refresh_wallet
        from penumbra_operator.queue import OperatorQueue

        sim = self.simulation
        operator_id = len(sim.agents)
        # If we're re-enabling, keep the existing agent + keypair; only
        # refresh wallet + inventory.
        if sim.operator_agent is None:
            spawn = int(next(iter(sim.arena.graph.nodes())))
            operator_agent = Agent(
                id=operator_id,
                position=spawn,
                policy=random_walk_policy,
                home=spawn,
            )
            sim.operator_agent = operator_agent
            # Append a fresh Dilithium keypair so the operator can sign +
            # verify just like the AI agents.
            self.keystore.keypairs.append(sig_keygen())
        else:
            operator_agent = sim.operator_agent

        # Wallet bootstrap / refresh.
        if self.market is not None:
            from penumbra_core.economy import Wallet

            if operator_id not in self.market.wallets:  # type: ignore[attr-defined]
                self.market.wallets[operator_id] = Wallet(  # type: ignore[attr-defined]
                    agent_id=operator_id, coins=self.operator_initial_coins
                )
            else:
                wallet = self.market.wallets[operator_id]  # type: ignore[attr-defined]
                wallet.coins = self.operator_initial_coins
                wallet.inventory = {}
            # Make sure the cargo cap covers the operator too.
            if self.cargo is not None and operator_id not in self.cargo.capacity:
                self.cargo.capacity[operator_id] = next(iter(self.cargo.capacity.values()), 20)

        queue = OperatorQueue()
        self.operator_queue = queue
        if self.market is not None and self.heatmap.dp_mechanism is not None:
            from penumbra_core.logistics import LogisticsMempool

            mempool = self.logistics_mempool or LogisticsMempool()
            self.operator_context = OperatorContext(
                simulation=sim,
                operator_agent=operator_agent,
                operator_agent_id=operator_id,
                market=self.market,  # type: ignore[arg-type]
                mempool=mempool,
                dp_mechanism=self.heatmap.dp_mechanism,
                keystore=self.keystore,
                initial_coins=self.operator_initial_coins,
                event_bus=self.event_bus,
                federated_trainer=self.federated_trainer,
            )
            refresh_wallet(self.operator_context)  # type: ignore[arg-type]

        # Wire pre-tick drain so queued actions land at the start of the
        # next tick. The closure captures self so a subsequent disable +
        # re-enable updates seamlessly.
        sim.pre_tick_hook = self._drain_operator_queue
        self.operator = object()  # marker so /operator/status returns enabled=True
        # Phase 6b Tier 6 — open a fresh session log so every action
        # the operator submits between now and disable is appended
        # to state/operator/sessions/<id>/actions.parquet.
        if self.operator_session_logger is None:
            from penumbra_operator.replay import SessionLogger

            self.operator_session_logger = SessionLogger()
        self.operator_session_id = self.operator_session_logger.start_session(  # type: ignore[attr-defined]
            scenario_id=None
        )
        return {
            "enabled": True,
            "operator_id": int(operator_id),
            "position": int(operator_agent.position),
            "session_id": str(self.operator_session_id),
        }

    def disable_operator(self) -> dict[str, object]:
        """Stop the queue drain; leave the slot in place for the next enable."""
        self.operator = None
        self.operator_queue = None
        # Keep the operator_agent + keypair + wallet in place so a
        # subsequent enable is a clean re-start without surprises.
        self.simulation.pre_tick_hook = None
        closed_session_id: str | None = None
        # Phase 6b Tier 6 — close the live session log (if any) and
        # write its final scorecard + meta.json out to disk.
        if (
            self.operator_session_logger is not None
            and self.operator_session_id is not None
            and self.operator_context is not None
        ):
            from penumbra_operator.scoring import OperatorScoreCard

            ctx = self.operator_context
            wallet = ctx.market.wallets.get(ctx.operator_agent_id)  # type: ignore[attr-defined]
            budget = ctx.dp_mechanism.budget  # type: ignore[attr-defined]
            scorecard = OperatorScoreCard.compute(
                coins_now=float(wallet.coins) if wallet is not None else 0.0,
                coins_start=float(ctx.initial_coins),  # type: ignore[attr-defined]
                epsilon_spent=float(budget.epsilon_spent),
                epsilon_total=float(budget.epsilon),
                attacks_survived=int(self.operator_attacks_survived),
                chain_contribution=int(self.operator_chain_contribution),
            )
            try:
                self.operator_session_logger.close_session(  # type: ignore[attr-defined]
                    self.operator_session_id, scorecard
                )
                closed_session_id = self.operator_session_id
            except Exception:
                logger.exception("operator session close failed for %s", self.operator_session_id)
            self.operator_session_id = None
        return {"enabled": False, "closed_session_id": closed_session_id}

    def _drain_operator_queue(self, current_tick: int) -> None:
        """Pre-tick hook: pop every due action, apply, log into the recent buffer."""
        queue = self.operator_queue
        ctx = self.operator_context
        if queue is None or ctx is None:
            return
        from penumbra_operator.actions import apply_action, coalesce_moves

        due = queue.pop_due(current_tick)  # type: ignore[attr-defined]
        if not due:
            return
        due = coalesce_moves(due)
        session_logger = self.operator_session_logger
        session_id = self.operator_session_id
        for action in due:
            try:
                result = apply_action(ctx, action)  # type: ignore[arg-type]
            except Exception:
                logger.exception("operator action %s crashed", action.kind)
                continue
            self.operator_recent_results.append(result)
            # Phase 6b Tier 6 — append (action, result) to the open session log.
            if session_logger is not None and session_id is not None:
                try:
                    session_logger.record(session_id, action, result)  # type: ignore[attr-defined]
                except Exception:
                    logger.exception("operator session record failed")
        # deque(maxlen=200) evicts oldest automatically — no cap-check
        # needed. Dashboard tile reads the last 50; 200 leaves headroom
        # for late consumers.
