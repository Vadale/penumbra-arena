# Inter-Silo Deep Integration — Phase 6a Plan

**Status**: planning, prerequisite to `OPERATOR_MODE_PLAN.md`.
**Effort**: ~50h across 5 tiers.
**Target window**: month 3-4 post-OSS-launch; before Phase 5
attack/defense work or in parallel.

**Sister docs**: `LOGISTICS_PLAN.md`, `FEDERATED_LEARNING_PLAN.md`,
`BENCHMARK_PLAN.md`, `SYNTHETIC_DATA_PLAN.md`,
`CRYPTO_ATTACK_DEFENSE_PLAN.md` (Phase 5),
`OPERATOR_MODE_PLAN.md` (Phase 6b, depends on this).

---

## 1. The problem

Penumbra today has **8 packages running in parallel** every tick.
They're individually correct but **only shallowly connected**.
Concrete examples of the shallowness:

| Producer | Consumer | Current connection | Why it's shallow |
|---|---|---|---|
| `analytics.dashboard_pipeline` GARCH | `core.economy.Market` | none | Volatility forecast doesn't influence ask prices |
| `analytics.dashboard_pipeline` Bayesian posterior | `learning.federated.FederatedTrainer.ingest()` | none | Greedy heuristic is used as label; posterior is ignored |
| `crypto.dp.DPMechanism` budget exhausted | `analytics.dashboard_pipeline` BERTopic / NumPyro | warn-and-continue | Should automatically downgrade / pause those consumers |
| `transport.agent_signing` signing_rejected > 0 | `core.economy.Market` BUY/SELL settle | none | Agent with bad sigs can still trade |
| `core.logistics_echelon` bullwhip_ratio | `learning.env.PenumbraEnv` observations | none | The MAPPO policy never sees upstream variance |
| `chain.node` block production | `core.economy.Market.treasury` | none | Match winner doesn't get any economic bonus from the chain |
| `learning.federated` aggregated FL weights | `learning.MappoRuntime` actor (inference) | none — FL trainer mutates only itself | Aggregated FL deltas should be *broadcastable* to the inference path |
| `core.logistics.LogisticsMempool` carrier earnings | `learning.env.RewardWeights` for MAPPO | indirect (shaper reads earnings, MAPPO reward includes shaper) | The shaper is in-tree but the live trainer's env doesn't see orchestrator's mempool — shaper is a no-op in the live trainer |

Net effect: each pillar is **observable** in the dashboard, but no
pillar is **load-bearing for any other**. The simulation looks alive
but the decision loops don't actually close.

## 2. Vision — what "deep integration" looks like

The same 8 packages, but with **explicit bidirectional channels** so:

- A market shock propagates through stats → reorder policy →
  carrier dispatch → MAPPO reward → policy gradient → next-tick
  action. **One causal chain across 5 pillars.**
- A signing breach immediately disables the affected agent's
  trades and triggers a Krum filter on the FL aggregator that
  *includes that agent's gradient*. **Security event drives both
  market and ML.**
- DP budget exhaustion makes downstream analytics (Bayesian,
  topics, monte_carlo) gracefully degrade to un-noised fallback or
  pause, and the dashboard shows WHY. **Crypto budget drives stats
  cadence.**

The orchestrator becomes a real **event router**, not a tick
scheduler that happens to call N independent step functions.

## 3. Architectural addition — `events.py`

**New module**: `packages/transport/penumbra_transport/events.py`

Tiny synchronous in-process event bus (no asyncio queue — runs
inline at analytics-tick rate, so back-pressure is the analytics
loop itself). API:

```python
from dataclasses import dataclass
from typing import Callable, Protocol

@dataclass(frozen=True, slots=True)
class Event:
    kind: str               # "garch.spike" | "signing.rejected" | ...
    tick: int
    payload: dict[str, object]

class EventHandler(Protocol):
    def __call__(self, event: Event) -> None: ...

class EventBus:
    def subscribe(self, kind: str, handler: EventHandler) -> None: ...
    def emit(self, event: Event) -> None: ...
    def stats(self) -> dict[str, int]: ...   # for dashboard tile
```

Orchestrator owns one `EventBus`. Each pillar that wants to react
subscribes at boot. Each pillar that produces signals emits during
its existing per-tick step.

Constraint: handlers must be **idempotent + side-effect-local** (no
recursive emits inside a handler; queue them for next tick).

---

## 4. Tier-by-tier — what closes loops

### Tier 1 — Stats ↔ Logistics + Stats ↔ Market (~12h)

**Goal**: market-data signals drive operational decisions.

**Code changes**:

1. `packages/analytics/penumbra_analytics/dashboard_pipeline.py`:
   - When GARCH conditional variance σ̂² jumps > 2× the rolling
     baseline, emit `Event(kind="garch.spike", payload={sigma, baseline, pid_affected: list[int]})`.
   - When the CPI / price index moves > 3 σ in 10 s, emit
     `Event(kind="cpi.shock", payload={delta, direction})`.
   - When wealth Gini > 0.7, emit `Event(kind="gini.high",
     payload={gini, top_decile_share})`.

2. `packages/core/penumbra_core/logistics.py:ReorderPolicy`:
   - New method `react_to_volatility(sigma_signal)` that
     temporarily multiplies the `s` (reorder point) by
     `(1 + sigma_signal)`, so a high-volatility regime triggers
     **earlier** reorders (defensive stocking).
   - Decay back to baseline over 60 s.

3. `packages/core/penumbra_core/economy.py:Market`:
   - New `pricing_regime: Literal["normal","volatile","crisis"]`
     attribute. On `garch.spike` event, transitions to "volatile"
     for 30 s — the `update_prices` step then uses tighter
     `_PRICE_MIN_RATIO` / `_PRICE_MAX_RATIO` bands so the
     defensive stocking doesn't induce a price spiral.

4. `orchestrator.py` wires the event bus and registers handlers in
   `Orchestrator.build`.

**New endpoint**: `GET /events/recent?limit=50` returns the last N
events for the dashboard event log.

**New tile**: `EventBusChart.tsx` — a streaming log of
`(tick, kind, summary)` rows. Visualises that signals *propagate*.

**Tests** (`packages/transport/tests/test_events_tier1.py`):
- GARCH spike emits one `garch.spike` event.
- `garch.spike` handler bumps `ReorderPolicy.s` by the expected
  fraction.
- Decay returns to baseline after the configured window.
- `cpi.shock` transitions `Market.pricing_regime`.
- Idempotency: handler called twice with the same event has the
  same effect as once.

### Tier 2 — Security ↔ Market + Security ↔ Logistics (~10h)

**Goal**: a security event has *teeth* in the economic loop.

**Code changes**:

1. `packages/transport/penumbra_transport/agent_signing.py`:
   - Track per-agent rejection count. When agent X exceeds
     `_TRADE_BLOCK_THRESHOLD = 3` rejections in 30 s, emit
     `Event(kind="agent.blocked", payload={agent_id, reason:
     "signing_rejected", until_tick})`.
   - The block lifts automatically after a configurable cool-off
     (default 60 s).

2. `packages/core/penumbra_core/economy.py:Market`:
   - New field `blocked_agents: set[int]`.
   - `settle_arrivals` BUY/SELL paths skip blocked agents (logged
     in pipeline as "blocked_trade_attempts" counter).

3. `packages/core/penumbra_core/logistics.py:assign_carriers`:
   - Skip blocked agents during dispatch (they can't carry while
     blocked).

4. `packages/learning/penumbra_learning/federated.py`:
   - Subscribe to `agent.blocked`; on receipt, zero-out that
     agent's local delta for the current round (so a compromised
     client can't poison the aggregate).

**New endpoint**: `GET /security/blocked-agents` →
`{blocked: [(agent_id, reason, until_tick), ...], history_count}`.

**New tile**: `BlockedAgentsChart.tsx` showing live block list +
historical block count per agent.

**Tests** (`test_events_tier2.py`):
- After 3 rejections in 30 s, agent X is in `Market.blocked_agents`.
- Blocked agent's BUY/SELL is no-op.
- Blocked agent skipped by `assign_carriers`.
- FL trainer's delta for blocked agent is zero at next aggregation.
- Block clears after cool-off; agent can trade + dispatch + train
  again.

### Tier 3 — DP-budget-aware analytics cadence (~10h)

**Goal**: when ε runs out, downstream consumers degrade
gracefully instead of just logging a warning.

**Code changes**:

1. `packages/crypto/penumbra_crypto/dp.py:DPMechanism`:
   - When budget < 5% remaining, emit
     `Event(kind="dp.budget.warning", payload={remaining, total})`.
   - When budget = 0, emit `Event(kind="dp.budget.exhausted",
     payload={total})`.

2. `packages/analytics/penumbra_analytics/dashboard_pipeline.py`:
   - On `dp.budget.warning`, halve the cadence of the heaviest
     consumers (GARCH 30s→60s, NumPyro 30s→60s, BERTopic 60s→120s).
   - On `dp.budget.exhausted`, switch to un-noised fallback (mark
     all subsequent releases with `dp_noise_applied=False`).

3. `packages/transport/penumbra_transport/orchestrator.py`:
   - Subscribe to both DP events; toggle a runtime flag
     `dp_degraded: bool` that the `/dp/budget` endpoint exposes.

4. `packages/learning/penumbra_learning/federated.py`:
   - On `dp.budget.exhausted`, refuse to start new DP-SGD rounds
     until a manual reset; existing FL rounds without DP continue.

**Endpoint additions**: `/dp/budget` payload now includes
`degraded: bool`, `degradation_reason: str | None`.

**Tile update**: existing `DPCompareChart` overlays a "degraded
mode" banner when active.

**Tests**:
- Synthetic ε drain triggers `dp.budget.warning` at the right
  threshold.
- Pipeline cadence halves; verify by counting consumer calls in a
  60 s simulated window.
- `dp.budget.exhausted` flips the `dp_noise_applied=False` flag
  in subsequent heatmap releases.
- FL trainer raises `DPBudgetExhaustedError` on next round start.

### Tier 4 — ML/RL ↔ Logistics reward feedback (~10h)

**Goal**: the LiveTrainer's MAPPO env actually sees the live
orchestrator's logistics + market state instead of running on a
de-coupled internal env.

**Code changes**:

1. `packages/learning/penumbra_learning/env.py:PenumbraEnv`:
   - New optional constructor argument `orchestrator: object | None
     = None`. When provided, the env's `step()` reads orchestrator's
     `logistics_mempool` + `demand` instead of the local stubs.
   - The shaper (`LogisticsRewardShaper`) becomes effective in the
     live trainer (currently no-op because shapr can't reach
     orchestrator state).

2. `packages/learning/penumbra_learning/live_trainer.py`:
   - On boot, attach to orchestrator and pass it to the internal
     env constructor.
   - Emit `Event(kind="ml.policy.updated", payload={iteration,
     mean_reward, kl})` after each PPO iter.

3. `orchestrator.py`:
   - Subscribe to `ml.policy.updated`; when reward jumps > 50 %
     vs baseline, the orchestrator emits a downstream
     `policy.improved` event that the Bench leaderboard tile
     surfaces as "live training is converging".

4. `packages/core/penumbra_core/logistics.py:assign_carriers`:
   - Add a hook: when an order is fulfilled, append (agent_id,
     reward) to a `recent_carrier_rewards: deque(maxlen=200)` on
     the mempool.
   - `LogisticsRewardShaper` reads from this deque to compute the
     dispatch bonus.

**Endpoint additions**:
- `GET /learning/carrier-reward-stream` — last N carrier rewards
  per agent.
- `GET /events/policy-improvements` — historical
  `policy.improved` events.

**Tile**: extend `RewardShapingChart` with a live carrier-rewards
sparkline per agent.

**Tests**:
- LiveTrainer's env, when given orchestrator, reads the actual
  mempool (verify by injecting a synthetic order + asserting it
  appears in env state).
- After a synthetic ML iter with high reward, `policy.improved`
  event is emitted exactly once.
- Shaper computes non-zero bonus for an agent that fulfilled an
  order in the rewards-deque window.

### Tier 5 — Chain-as-event-source + cross-pillar observability (~8h)

**Goal**: the blockchain isn't a passive ledger; block production
drives economic + ML events.

**Code changes**:

1. `packages/chain/penumbra_chain/node.py:produce_block`:
   - On successful block append, emit
     `Event(kind="chain.block.finalised", payload={height,
     n_outcomes, winners: list[int]})`.
   - On slashing, emit
     `Event(kind="chain.validator.slashed", payload={validator_id,
     evidence_height})`.

2. `packages/core/penumbra_core/economy.py:Market`:
   - Subscribe to `chain.block.finalised`; for each winner agent
     in the payload, credit a `+_BLOCK_REWARD_COINS` (default 10)
     to their wallet. This makes the blockchain economically
     meaningful: winning matches → on-chain reward → real wealth
     change visible in Gini + wealth distribution.

3. `packages/learning/penumbra_learning/federated.py`:
   - Subscribe to `chain.validator.slashed`; if the slashed
     validator happens to be a registered FL participant
     (unlikely in single-process; possible if FL extended to
     validator network), zero its delta.

4. **Cross-pillar observability tile**:
   - `EventGraphChart.tsx` — a directed graph showing which events
     have fired in the last 5 minutes and which handlers reacted
     to them. Lays bare the live causal structure.
   - Powered by `EventBus.stats()` exposed via
     `GET /events/graph`.

**Tests**:
- A match-end → chain block → market wallet credit chain fires
  end-to-end on a single tick.
- Slashing event observed by FL trainer (mock subscriber asserts
  receipt).
- `EventBus.stats()` returns non-zero counts for both producers
  and consumers after a 5 s synthetic run.

---

## 5. Memory + perf budget

- `EventBus` keeps a `deque(maxlen=1024)` of recent events; ~50 KB
  steady state. Handlers run inline at 1 Hz analytics cadence so
  no extra threads.
- `recent_carrier_rewards` deque: 200 × 32 B = 6 KB.
- `blocked_agents` set: bounded by `n_agents` (50) → trivial.
- Tick budget impact: each handler must complete < 1 ms; the bus
  records p99 latency per handler kind in `stats()` so regressions
  surface in the EventBus tile.

## 6. Acceptance criteria

- One end-to-end cross-pillar story runs without manual stitching:
  inject a synthetic GARCH spike → ReorderPolicy retunes →
  carriers re-dispatch → carrier rewards flow → MAPPO reward
  changes → next-tick MAPPO action distribution shifts. All
  visible in the EventGraphChart tile.
- ~30 new tests; all green.
- 0 pyright errors, 0 ruff errors, biome clean.
- Stress-test post-Tier-5: tick rate not regressed > 5 % vs current
  baseline (7.64 Hz → ≥ 7.26 Hz acceptable). If regression > 10 %,
  the handler with the worst p99 latency is the culprit; profile
  + optimise.

## 7. Out of scope (Phase 6a)

- Distributed event bus (Kafka/Redis/NATS) — single-process only.
- Persisted event log to disk — in-memory deque only.
- Event replay / time-travel — Phase 6b (Operator Mode) does this
  on the world snapshot level.
- Event-driven rule engine / DAG visualisation beyond the 5-min
  window.
- WebSocket push of events to the dashboard — polling
  `GET /events/recent?limit=50` is enough for the dashboard at
  1 Hz; WS would only matter if we wanted reactive UI for the
  Operator Console (deferred to Phase 6b).
