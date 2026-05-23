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
    market: object | None = field(default=None, init=False)
    cargo: CargoConstraints | None = field(default=None, init=False)
    demand: DemandModel | None = field(default=None, init=False)
    reorder_policy: ReorderPolicy | None = field(default=None, init=False)
    logistics_mempool: LogisticsMempool | None = field(default=None, init=False)
    echelon_network: EchelonNetwork | None = field(default=None, init=False)
    federated_trainer: object | None = field(default=None, init=False)
    _logistics_lead_time_ticks: int = field(default=5, init=False)
    _logistics_iteration: int = field(default=0, init=False)

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
                    # Drive one market tick: production + price update +
                    # settle sells & buys for any agent that just moved.
                    if self.market is not None:
                        agent_positions = {a.id: a.position for a in self.simulation.agents}
                        rng = self.simulation.seeded.numpy_for("economy")
                        trades = self.market.tick(  # type: ignore[attr-defined]
                            tick=self.simulation.tick_counter,
                            agent_positions=agent_positions,
                            rng=rng,
                        )
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
                    await asyncio.to_thread(self.pipeline.recompute)
                    # Sign + verify the current tick's moves. The protocol
                    # demo is per-tick even though analytics is per-second
                    # because the heatmap is the cadence we already pay.
                    await asyncio.to_thread(self.sign_and_verify_moves)
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
