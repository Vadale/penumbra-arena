# Operator Mode — Phase 6b Plan

**Status**: planning. Depends on `INTER_SILO_INTEGRATION_PLAN.md`
(Phase 6a). Builds on `CRYPTO_ATTACK_DEFENSE_PLAN.md` (Phase 5)
when available.
**Effort**: ~60h across 6 tiers.
**Positioning**: **NOT a videogame.** This is a "cyber range /
tabletop drill" surface — TryHackMe / Cyberbit / RangeForce
analogue. The audience is privacy engineers, MPC custodians,
trading-desk risk teams, and CS / security students. Replayable
scenario-based exercises with measurable outcomes, not
entertainment.

**Sister docs**: `LOGISTICS_PLAN.md`, `FEDERATED_LEARNING_PLAN.md`,
`BENCHMARK_PLAN.md`, `SYNTHETIC_DATA_PLAN.md`,
`CRYPTO_ATTACK_DEFENSE_PLAN.md`, `INTER_SILO_INTEGRATION_PLAN.md`.

---

## 1. Concept

A human user takes control of an **external operator agent** (id
N+1, i.e. agent #50 if `n_agents=50`) that lives alongside the
existing MAPPO + heuristic agents. The operator has access to
**every pillar's primitive operations** via a Console UI and a
`pno` CLI:

- **Market**: buy / sell / inspect prices / monitor wealth.
- **Logistics**: dispatch orders / cancel assignments / inspect
  fill-rate / retune (s, S) live.
- **Crypto**: sign messages (Dilithium), encrypt aggregates
  (CKKS), prove via Groth16, issue DP queries, consume privacy
  budget.
- **ML**: inject custom policies for owned slot, observe MAPPO
  policy distributions, train a private branch.
- **Attacks** (when Phase 5 ships): launch replay / Byzantine /
  DP-recon / linkability / SNARK forgery against any visible
  target.
- **Defenses**: enable k-anonymity / padding / GAN-poisoning /
  request obfuscation on owned data streams.

The 50 MAPPO/heuristic agents **keep competing** between
themselves. The operator is an asymmetric extra entity that the
simulation reacts to. Scoring is **multi-axis composite**: profit,
privacy budget preserved, attacks survived, chain stability, no
single-objective max-able by ignoring the others.

## 2. Why "Operator", not "Player"

- Replay-driven: every scenario is reproducible from `(seed,
  scenario_id, operator_action_log)`.
- Instrumented: per-tick metric stream, exportable as parquet for
  post-mortem.
- Measurable: scoring rubric is public + composite so it can't be
  cheesed.
- Pedagogical: each action surfaces the *educational pillar* it
  touches (clicking "issue DP query" pops a sidebar with the
  Laplace mechanism math + current ε accountant).
- B2B narrative: "tabletop drill for your privacy ops team" sells
  better than "video game" to BBVA, MPC-custody firms, EU AI Act
  compliance consultancies.

## 3. Architectural addition — Operator agent slot

### 3.1 Backend: `packages/operator/penumbra_operator/__init__.py`

A new package. Why a new package and not a module inside
`transport/` or `attacker/`? Because the operator is a **first-
class participant** in the simulation, not a debug tool. Same shape
as `learning/` or `attacker/` so a future "Operator-Bench"
benchmark can compare different *operator strategies* the way
Penumbra-Bench compares MAPPO checkpoints today.

### 3.2 The slot

`Simulation.operator_agent: Agent | None = None`, lazy-built on
first `/operator/enable` POST. When non-None, the operator agent
is included in the per-tick loop:

- Its `position` is mutable from `/operator/move` calls.
- Its `wallet` lives in `Market.wallets[OPERATOR_ID]`.
- It owns a `Dilithium` keypair via the standard keystore.
- Its action queue is read at the START of each tick (any actions
  the operator submitted between ticks are applied; conflicts
  resolved deterministically).
- It does NOT have a MAPPO policy attached; its actions come from
  the queue, period.

### 3.3 Action queue

`packages/operator/penumbra_operator/queue.py`:
- `OperatorAction` dataclass: `kind`, `payload`, `submit_tick`,
  `target_tick: int | None`. Actions can be scheduled for a
  specific tick or for "next available".
- `OperatorQueue` is a simple FIFO with a `pop_due(tick)` method.
- Thread-safe (CLI + dashboard can both submit concurrently).

### 3.4 Scoring

`packages/operator/penumbra_operator/scoring.py`:
- `OperatorScoreCard`:
  - `profit`: `wallet.coins` at end vs start.
  - `privacy_preserved`: 1 − (ε_spent / ε_total).
  - `attacks_survived`: count of attacks that didn't compromise
    the operator (sig verifies, DP queries below threshold,
    etc.).
  - `chain_contribution`: blocks the operator (as validator)
    finalised correctly.
  - `composite`: weighted sum, weights documented +
    survey-validated.

## 4. Tier-by-tier — what ships

### Tier 1 — Operator agent + 8 core actions (~12h)

**New module**: `packages/operator/penumbra_operator/actions.py`.

Action catalogue (the V1.0 catalogue; extended in Tier 3/4):

| Action kind | Payload | Effect |
|---|---|---|
| `move` | `{target_node: int}` | Moves operator to neighbour (cost deducted from wallet). |
| `buy` | `{product: int, qty: int}` | Settles a BUY at current city if possible. |
| `sell` | `{product: int, qty: int}` | Settles a SELL at current city. |
| `dispatch_order` | `{city: int, product: int, qty: int, reward: float}` | Places an order in `LogisticsMempool` assigned to operator. |
| `cancel_assignment` | `{order_id: int}` | Releases an assigned order back to unassigned pool. |
| `query_dp` | `{statistic: str, epsilon: float}` | Issues a DP-noised query; deducts ε. |
| `sign` | `{message: bytes}` | Returns operator's Dilithium signature. |
| `verify` | `{message: bytes, sig: bytes, public_key: bytes}` | Returns bool. |

**New endpoint family**: `POST /operator/*` for each action +
`GET /operator/status` (state mirror) + `POST /operator/enable` +
`POST /operator/disable`.

**New `pno` CLI**: `uv tool install ./packages/operator`. Mirrors
the endpoints; sub-commands `pno move 12`, `pno buy bread 3`,
`pno dispatch ...`, etc.

**Tests** (`packages/operator/tests/test_actions.py`):
- Enable/disable lifecycle.
- Each action's success path.
- Each action's failure path (insufficient coins, no path, ε
  exhausted, etc.) returns structured error JSON.
- Concurrency: 100 queued actions in one tick are applied in
  submission order, no race.
- `pno` CLI smoke (one happy-path action per kind).

### Tier 2 — Operator Console UI (~12h)

**New React route**: `apps/web/src/pages/Operator.tsx` (path
`/operator`).

Layout:

```
┌─ Operator Status ───────────────────┐  ┌─ Action Builder ───┐
│ position: 12   coins: 245           │  │ kind: [dropdown]   │
│ ε remaining: 0.85   inventory: {…}  │  │ payload: [form]    │
│ signing: 12 ok / 0 bad              │  │ [Submit]           │
└──────────────────────────────────────┘  └────────────────────┘
┌─ Action Log (last 50) ───────────────────────────────────────┐
│ tick 1248 │ buy(bread, 3)        │ ✓ 12 coins                │
│ tick 1250 │ query_dp(cpi, 0.05)  │ ✓ value=12.4 ± noise      │
│ tick 1252 │ dispatch_order(...)  │ ✓ assigned to operator    │
└───────────────────────────────────────────────────────────────┘
┌─ Live World State Mirror (the 50 other agents) ──────────────┐
│ [embedded mini-version of Dashboard panels]                  │
└───────────────────────────────────────────────────────────────┘
┌─ Score Card ─────────────────────────────────────────────────┐
│ profit: +245   privacy: 0.85   survived: 0   chain: 12       │
│ composite: 0.62                                              │
└───────────────────────────────────────────────────────────────┘
```

Mini-dashboard inside Operator page reuses existing chart
components (no duplication).

**Tests** (vitest):
- Form submission posts to right endpoint.
- Action log updates in real time (WS or 1 s polling).
- Score card refreshes with operator status.

### Tier 3 — Attack actions (~8h, depends on Phase 5)

When `CRYPTO_ATTACK_DEFENSE_PLAN.md` ships its attack modules,
expose each as an operator action:

| Action kind | Payload | Effect |
|---|---|---|
| `attack_replay` | `{target_signature: hex, replay_offset: int}` | Attempts replay against target's signing surface. |
| `attack_byzantine` | `{n_equivocations: int}` | If operator is a validator, equivocate on N blocks. |
| `attack_dp_recon` | `{target_agent: int, query_log: list}` | Runs Dinur-Nissim reconstruction; reports recovered bits. |
| `attack_linkability` | `{feature_set: list, target_agent: int}` | Runs the 1-NN / HMM matcher; reports accuracy. |
| `attack_membership` | `{target_observation: array}` | Membership-inference attack on MAPPO policy. |
| `attack_snark_forge` | `{circuit: str}` | Attempts SNARK forgery; reports verifier decision. |

Each attack action also emits an `Event(kind="operator.attack", …)`
on the inter-silo event bus (Phase 6a) so the simulated victim
+ the dashboard event log both surface it.

**Tests**: each attack returns a structured `AttackResult` with
`accepted: bool` + `evidence: dict` + `defender_response: str`.

### Tier 4 — Defense actions (~8h, depends on Phase 5)

| Action kind | Payload | Effect |
|---|---|---|
| `defense_k_anonymity` | `{k: int, statistic: str}` | Enables k-anon bucketing on a downstream statistic. |
| `defense_padding` | `{kind: "request"\|"response", size: int}` | Adds padding to outgoing messages. |
| `defense_gan_poison` | `{rate: float, target_stat: str}` | Trains/uses small CycleGAN to inject decoy traces. |
| `defense_pause_dp` | `{}` | Pauses the operator's DP queries until manual resume. |
| `defense_rotate_keys` | `{}` | Generates fresh Dilithium keypair; old one invalidated. |
| `defense_enable_krum` | `{f: int}` | If operator participates in FL, forces Krum aggregator. |

**Tests**: each defense reduces the corresponding attack's success
in a paired (attack → defense → attack) regression test.

### Tier 5 — Scenario engine + 12 starter scenarios (~12h)

**New module**: `packages/operator/penumbra_operator/scenarios.py`.

Scenario YAML schema (`packages/operator/scenarios/*.yaml`):

```yaml
id: scn-001-bullwhip-defender
title: "Defend agent_12 from a bullwhip-leak chain"
difficulty: medium
description: |
  A simulated adversary will exploit the bullwhip effect to
  de-anonymise agent_12. You have 5 minutes to deploy
  countermeasures and reduce the attacker's success below 20 %.
setup:
  seed: 42
  n_agents: 50
  preconditions:
    - market.pricing_regime: "volatile"
    - logistics.echelon.bullwhip_ratio: ">1.5"
opening_event:
  kind: "operator.scenario.start"
  payload: {target_agent: 12, attacker_strategy: "bullwhip"}
victory:
  - attacker_accuracy < 0.20  before tick 3000
  - operator.privacy_preserved > 0.7
failure:
  - operator.coins < -100
  - attacker_accuracy > 0.80
allowed_actions: ["defense_*", "query_dp", "sign", "verify"]
scoring:
  weights:
    survival: 0.4
    privacy_preserved: 0.3
    profit: 0.2
    chain_contribution: 0.1
```

12 starter scenarios spanning 4 difficulty tiers (3 each):

1. `scn-001-bullwhip-defender` (defense)
2. `scn-002-dp-recon-attacker` (attack)
3. `scn-003-byzantine-validator` (chain)
4. `scn-004-replay-the-leader` (chain attack)
5. `scn-005-linkability-attacker` (privacy attack)
6. `scn-006-membership-inference-defender` (ML defense)
7. `scn-007-fl-backdoor-injector` (FL attack)
8. `scn-008-fl-backdoor-detector` (FL defense)
9. `scn-009-trade-bot-market-maker` (pure logistics)
10. `scn-010-snark-forge-attempt` (crypto attack)
11. `scn-011-cross-pillar-defender` (HARD; needs Tier 6a fully)
12. `scn-012-zero-day-improv` (open-ended; no fixed victory; pure
    sandbox for instructor-led sessions)

**New endpoints**:
- `GET /operator/scenarios` — list all scenarios.
- `POST /operator/scenarios/{id}/start` — bootstrap the
  preconditions + emit `opening_event`.
- `POST /operator/scenarios/{id}/abandon`.
- `GET /operator/scenarios/{id}/status` — real-time progress
  vs victory/failure clauses.

**Tile**: `OperatorScenarioChart.tsx` — list + start button +
live progress meters + the per-scenario leaderboard.

**Tests**:
- Each scenario boots to its preconditions.
- A scripted "winning" sequence of operator actions resolves to
  victory.
- A scripted "losing" sequence hits the failure clause.
- Abandoned scenarios are deterministically cleaned up (no
  leaked state into the next run).

### Tier 6 — Replay log + cross-session leaderboard (~8h)

**New module**: `packages/operator/penumbra_operator/replay.py`.

- Every operator action is logged as
  `(tick, kind, payload, success)` to
  `state/operator/sessions/<session_id>/actions.parquet`.
- Session metadata includes the world snapshot at start, the
  scenario id, the final scorecard.
- `pno replay <session_id>` re-runs the recorded actions against
  a fresh simulation seeded identically; the resulting scorecard
  must match the original within `±ε` (regression test for
  determinism).

**Endpoint**: `GET /operator/sessions` + `GET
/operator/sessions/{id}/replay`.

**Tile**: `OperatorLeaderboardChart.tsx` — top-N by composite
score per scenario, click row to download the replay parquet.

**Tests**:
- Determinism: replay produces identical final state.
- Session metadata parquet schema-stable.

---

## 5. Integration with prior phases

| Pillar / Phase | What Operator Mode uses |
|---|---|
| Phase 2.5 logistics | `dispatch_order`, `cancel_assignment` actions go through `LogisticsMempool` + `assign_carriers` |
| Phase 2.5 FL | Operator can join as an FL participant via `attack_byzantine` (poisoned client) or `defense_enable_krum` (Byzantine-robust aggregator) |
| Phase 2.5 bench | `OperatorScoreCard.composite` becomes a Penumbra-Bench task in v2.0 |
| Phase 3 stress test | The scenario engine runs as a stress-test workload (high action throughput from the queue) |
| Phase 4 launch materials | Operator Mode shipping = v2.0 launch event; arXiv paper update; new HN post |
| Phase 5 crypto attack/defense | Tier 3 + Tier 4 of this plan are literally the operator-facing surfaces for those modules |
| Phase 6a inter-silo events | Operator actions emit `operator.*` events on the bus; the simulation reacts via the same handlers built for AI-driven events |

The operator is the **manual driver** of the event bus the
inter-silo work installs. **You cannot ship Operator Mode without
Phase 6a; you can ship 6a without Operator Mode.**

## 6. Memory + perf budget

- Action queue: bounded `deque(maxlen=4096)`. ~200 KB.
- Session log: streamed to parquet, not held in RAM beyond a
  ~512-action window. ~50 KB.
- Operator agent: same memory footprint as a regular agent.
- Score card recomputation: O(1) per tick (sum of running
  counters). Negligible.
- Tick budget impact: < 0.5 ms per tick. Acceptable.

## 7. Acceptance criteria

- All 12 starter scenarios bootable + scripted-winnable +
  scripted-losable.
- 50 + new tests; all green.
- Determinism: replay match within 1 ε of any decimal metric.
- `pno` CLI installable + functional from a clean checkout.
- Operator Console UI loads in < 2 s and responds < 100 ms per
  action submit.
- Documentation: `packages/operator/README.md` + one tutorial-
  style lesson YAML in `packages/shell_coach/lessons/12_operator.yaml`
  that walks through scenario 1.

## 8. Positioning + business angle

This is the **commercial differentiator**. With Operator Mode
shipped, Penumbra is the *only* OSS tool I know of that combines:
- Live multi-agent simulation
- Real crypto stack (CKKS/Dilithium/BLS/Groth16/FROST/...)
- Adversarial-robustness benchmark
- Interactive operator surface for tabletop drills

Target buyers (Phase 7 — commercialisation):
- **Banks / MPC custodians**: tabletop drill for the next FROST
  key-share corruption incident.
- **EU AI Act compliance teams**: documented adversarial-
  robustness measurement per Article 15.
- **Privacy regulators / data protection officers**: hands-on lab
  for evaluating DP-protected systems.
- **University courses**: replace 3 separate codebases (RL +
  crypto + chain) with one.
- **Cyber-range vendors** (Cyberbit, Immersive Labs, RangeForce):
  white-label the operator surface as an add-on.

Pricing model (out of scope here): freemium with paid scenarios +
private leaderboard for enterprise SSO. See
`OSS_LAUNCH_ROADMAP.md` Phase L4 sustainment for the playbook.

## 9. Out of scope (Phase 6b)

- Multi-operator multiplayer (cooperative or competitive). The
  asymmetric N AI + 1 human design is intentional — adding
  human-vs-human turns this into a multiplayer game which is a
  different product.
- Persistent operator identity / OAuth — session-scoped first;
  OAuth only if leaderboard traction justifies it.
- Time-warp / replay during a live session — replay is a separate
  endpoint, not a "rewind during play" feature.
- Mobile / responsive Operator UI — desktop-only at v2.0.
- 3D Operator avatar in the r3f arena view — operator is a regular
  agent visually; the differentiation is in the console panel.
