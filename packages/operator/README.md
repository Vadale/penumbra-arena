# penumbra-operator

**Phase 6b Tier 1** — the operator agent + 8 core actions + the `pno` CLI.

## Concept taught

A *tabletop drill* is a reproducible adversarial-robustness exercise.
The operator agent is a regular `Agent` instance (id = `n_agents`)
that lives alongside the MAPPO + heuristic agents and walks through
the same simulation paths; the only difference is that its actions
come from an `OperatorQueue` populated by a human (this CLI, or the
Operator Console in Tier 2) rather than a learned policy.

Server-side validation is what makes the exercise honest: handlers
return structured errors (insufficient coins, no path, ε exhausted)
instead of half-applying. Each handler is capped at **50 ms** of
wall-clock time; anything over budget is tagged `skipped=True` and
logged so a buggy action can't stall the tick loop.

## Installation

```sh
uv tool install ./packages/operator
pno --help
```

## CLI ↔ endpoint mapping

| `pno` sub-command                              | HTTP endpoint                       |
|------------------------------------------------|-------------------------------------|
| `pno enable`                                   | `POST /operator/enable`             |
| `pno disable`                                  | `POST /operator/disable`            |
| `pno status`                                   | `GET  /operator/status`             |
| `pno move <node>`                              | `POST /operator/move`               |
| `pno buy <product> <qty>`                      | `POST /operator/buy`                |
| `pno sell <product> <qty>`                     | `POST /operator/sell`               |
| `pno dispatch <city> <product> <qty> <reward>` | `POST /operator/dispatch_order`     |
| `pno cancel <order_id>`                        | `POST /operator/cancel_assignment`  |
| `pno query-dp <statistic> <epsilon>`           | `POST /operator/query_dp`           |
| `pno sign <hex>`                               | `POST /operator/sign`               |
| `pno verify <msg> <sig> <pk>`                  | `POST /operator/verify`             |

## Tier 1 action catalogue (8 actions)

| Kind                 | Payload                                       | Effect |
|----------------------|-----------------------------------------------|--------|
| `move`               | `{target_node: int}`                          | Moves the operator to a neighbour; cost deducted from wallet. |
| `buy`                | `{product: int, qty: int}`                    | Settles a BUY at the current city. |
| `sell`               | `{product: int, qty: int}`                    | Settles a SELL at the current city (city pays bid = 85% of ask). |
| `dispatch_order`     | `{city, product, qty, reward}`                | Places an order in `LogisticsMempool`, pre-assigned to the operator. |
| `cancel_assignment`  | `{order_id: int}`                             | Releases an assigned order back to the unassigned pool. |
| `query_dp`           | `{statistic: str, epsilon: float}`            | Issues a DP-noised query (Laplace); deducts ε from the budget. |
| `sign`               | `{message: hex}`                              | Returns the operator's Dilithium signature on `message`. |
| `verify`             | `{message, sig, public_key}`                  | Verifies a Dilithium signature; returns `verified: bool`. |

Available `query_dp` statistics in Tier 1:
`money_supply`, `price_index`, `n_pending_orders`, `operator_coins`.

## Action queue semantics

- Actions submitted between ticks are popped + applied at the START
  of the next tick, in `(submit_tick, insertion_sequence)` order.
- Conflicting moves in the same tick are coalesced: only the LAST
  `move` is applied. Buy / sell / dispatch / cancel / query_dp /
  sign / verify can all repeat freely.
- `target_tick` (optional) defers an action until a specific tick.
- The queue is bounded at `DEFAULT_MAX_QUEUE = 4096` entries; older
  entries are dropped if a runaway client over-submits.

## Lifecycle

- `POST /operator/enable` bootstraps a fresh wallet
  (`initial_coins = 100.0`), a fresh Dilithium keypair (appended to
  the `AgentKeystore`), and an empty inventory.
- A re-enable refreshes the wallet to its initial state but reuses
  the existing keypair so signatures stay verifiable across the
  lifecycle.
- `POST /operator/disable` stops drain but leaves the slot in place
  so the next enable is a clean re-start.

## Out of scope for Tier 1

- Attack actions (Tier 3 — depends on Phase 5 Tier 2).
- Defense actions (Tier 4 — depends on Phase 5 Tier 3).
- Operator Console UI (Tier 2).
- Scenario engine + 12 starter scenarios (Tier 5).
- Replay log + cross-session leaderboard (Tier 6).
