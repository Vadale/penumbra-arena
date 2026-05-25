# Penumbra — Logistics Extension Plan

A detailed, phase-by-phase blueprint for turning Penumbra's existing market
into a fully-fledged operations-research / supply-chain simulation lab.

**Status**: **SHIPPED 2026-05-23** (Tier 1-4). See `CHANGELOG.md`
"Logistics layer" section and `packages/core/penumbra_core/logistics*.py`
for the actual implementation. This document is the original
specification kept for reference; the as-shipped behaviour may differ
in detail from the design sketched below.

Sister documents:
- `ROADMAP.md` — the historical build plan and where we are
- `PROMPTING_GUIDE.md` — per-module implementation recipes
- `CLAUDE.md` — project-wide conventions

---

## 1. Motivation

Penumbra already simulates a closed two-sided market: 50 agents move on a
50-node graph, cities stock products with dynamic ask prices, money is
conserved, and the OU process drifts edge costs. From a logistics
perspective we have **all the structural primitives** of a transportation
network — we are just missing the OR-specific abstractions:

- vehicle capacity constraints
- demand curves per node
- reorder policies (s, S) / (Q, R)
- service-level / fill-rate KPIs
- supply-chain optimization benchmarks
- bullwhip-effect measurement

Adding these turns Penumbra into a unique pedagogical artefact: a
simulation lab where the same 50 agents teach **crypto** AND **supply
chain** without changing the runtime.

The strategic value:
- Doubles the addressable audience (SCM managers, OR researchers,
  industrial engineers, treasury teams) for both Edu B2B and OSS routes.
- Almost no hands-on supply chain simulations exist in OSS (SimPy too
  low-level; AnyLogic/Simul8 commercial only).

## 2. What Penumbra already provides (don't rebuild)

| Existing abstraction | Logistics equivalent |
|---|---|
| `Arena` graph + `cost_of(u, v)` | Transportation network with edge costs |
| `MarketState` (city) `inventory`, `treasury`, `ask_price` | Warehouse with stock + cash + price |
| `Wallet` (agent) `inventory`, `coins` | Vehicle / carrier with cargo + capital |
| `Trade` (buy/sell event) | Order fulfilled (sale or pickup) |
| `Market.tick()` produce → reprice → settle | Per-tick state update |
| OU drift on edge costs | Stochastic transport cost |
| CPI / inflation index | Macro price signal |
| `LiveTrainer` + `RewardWeights` | RL-based dispatching agent |

Concrete file paths:
- `packages/core/penumbra_core/economy.py` — `Market`, `Wallet`,
  `MarketState`, `Trade`, `Product`, `PRODUCT_CATALOG`
- `packages/core/penumbra_core/arena.py` — `Arena`, edge cost dynamics
- `packages/analytics/penumbra_analytics/dashboard_pipeline.py` —
  consumers we'll extend with logistics KPIs
- `packages/transport/penumbra_transport/orchestrator.py` — drives
  `market.tick()` each analytics tick

## 3. Conceptual model — what we add

### 3.1 Vehicle capacity
Today `Wallet.inventory: dict[int, int]` is unbounded. Add:
```python
@dataclass(slots=True)
class Wallet:
    agent_id: int
    coins: float
    inventory: dict[int, int]
    # NEW
    cargo_capacity: int  # max total units across all products
    weight_per_unit: dict[int, float]  # per-product weight
```
- `cargo_capacity` enforced on buy: agent can't buy more than `capacity - sum(inventory.values())`.
- Different agents can have different capacities → fleet heterogeneity.

### 3.2 Demand curves per city
Today cities only RECEIVE inventory (from production); buyers are the
agents that happen to arrive. Add intrinsic demand:
```python
@dataclass(slots=True)
class MarketState:
    # ... existing fields ...
    # NEW
    demand_rate: dict[int, float]   # units consumed per tick per product
    backlog: dict[int, int]          # unmet demand accumulated
```
Each tick:
- For each stocked product: `consumed = min(demand_rate[p], inventory[p])`
- If `consumed < demand_rate[p]`: `backlog[p] += demand_rate[p] - consumed` (stockout)
- City pays itself `consumed * ask_price[p]` (revenue) and the treasury increases.

This creates a real **end-customer demand signal**, distinct from agent
trading. Agents now serve as carriers / arbitrageurs.

### 3.3 (s, S) reorder policies
Per (city, product), define `s` (reorder point) and `S` (order-up-to).
When `inventory[p] < s[p]`, the city emits an `Order(city, product,
quantity = S[p] - inventory[p])` into a `LogisticsMempool`. Agents (or
the central planner) can fulfil orders.

```python
@dataclass(slots=True)
class Order:
    id: int
    city: int
    product: int
    quantity: int
    placed_tick: int
    fulfilled_tick: int | None  # None until delivered
    reward: float  # payable to fulfilling carrier
```

### 3.4 Supplier nodes (Tier 3)
A subset of nodes (e.g. 10 of 50) becomes **suppliers** that produce
products at NO cost (raw material source). Cities become **retailers**
that order from suppliers. This is the classic 2-echelon supply chain.

In Tier 3 we'd extend to N echelons (supplier → distributor → retailer
→ customer) to demonstrate the bullwhip effect.

### 3.5 KPI suite
- **Fill rate** = served_demand / total_demand per city per product
- **Inventory turnover** = sum(sales) / avg(inventory) per product
- **Stockout count** = days inventory hit zero per product
- **Holding cost** = inventory × holding_cost_per_unit per tick
- **Stockout cost** = backlog × stockout_cost_per_unit per tick
- **Order lead time** = fulfilled_tick − placed_tick per Order
- **Optimality gap** = (mappo_total_cost − vrp_optimal_cost) / vrp_optimal_cost
- **Bullwhip ratio** = variance(orders) / variance(sales) per echelon

## 4. Tier-by-tier implementation

### Tier 1 — Logistics base (~3-5h) — **SHIPPED 2026-05-23**

Implementation:
- `packages/core/penumbra_core/logistics.py` — `CargoConstraints`,
  `DemandModel`, `Order`, `LogisticsMempool`, `ReorderPolicy`
  ((s,S) policy), plus the four KPI report dataclasses + their
  `compute_*` functions.
- `packages/transport/penumbra_transport/orchestrator.py` — owns
  the live `cargo`, `demand`, `reorder_policy`, `logistics_mempool`;
  `_step_logistics()` runs once per analytics tick (1 Hz): demand
  consumption → reorder evaluation → 5-tick-lead-time fulfilment.
- `packages/transport/penumbra_transport/api.py` — six endpoints
  under `/logistics/*` (fill-rate, inventory-health, orders,
  reorder-policy GET/POST, capacity).
- `apps/web/src/charts/Logistics{FillRate,InventoryHealth,Orders,
  ReorderPolicy,Capacity}Chart.tsx` — five DetailModal tiles wired
  into AnalyticsPanel.
- `packages/core/penumbra_core/economy.py` — Market.settle_arrivals
  BUY path now caps qty by `cargo.available(agent_id, inventory)`.

Tests (all green):
- `packages/core/tests/test_logistics.py` — 11 unit tests covering
  cargo, demand, mempool, reorder policy + KPI computations.
- `packages/transport/tests/test_logistics_fl_endpoints.py` —
  endpoint integration tests.

**New file**: `packages/core/penumbra_core/logistics.py`

```python
"""Logistics layer on top of the existing market.

Concept taught: how an OR-style supply chain emerges from primitive
nodes + capacity + demand + reorder policies. The existing Market
becomes the physical layer; this module adds the operational layer.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Final

# Default cargo capacity per agent (units). Heterogeneous fleet later.
DEFAULT_CARGO_CAPACITY: Final[int] = 20

@dataclass(slots=True)
class CargoConstraints:
    """Per-agent cargo capacity. Stored on the Market alongside wallets."""
    capacity: dict[int, int]  # agent_id -> max units

    def available(self, agent_id: int, current_inventory: dict[int, int]) -> int:
        used = sum(current_inventory.values())
        return max(0, self.capacity.get(agent_id, DEFAULT_CARGO_CAPACITY) - used)


@dataclass(slots=True)
class DemandModel:
    """Per-city per-product demand rate and backlog tracking."""
    rate: dict[tuple[int, int], float]      # (city, product) -> units/tick
    backlog: dict[tuple[int, int], int] = field(default_factory=dict)
    served_history: list[int] = field(default_factory=list)
    requested_history: list[int] = field(default_factory=list)

    def step(self, market: object, tick: int) -> dict[str, float]:
        """Consume from city inventory; track unmet demand."""
        served = 0
        requested = 0
        # ... iterate (city, product) pairs in self.rate, deplete inventory,
        #     accumulate served/requested, update backlog
        ratio = served / max(requested, 1)
        return {"fill_rate": ratio, "stockouts": requested - served}


@dataclass(slots=True)
class Order:
    """Pending purchase from a city to be fulfilled by a carrier."""
    id: int
    city: int
    product: int
    quantity: int
    placed_tick: int
    reward: float
    fulfilled_tick: int | None = None
    fulfilled_by: int | None = None  # agent_id


@dataclass(slots=True)
class LogisticsMempool:
    """Outstanding orders waiting for a carrier to fulfil."""
    pending: list[Order] = field(default_factory=list)
    fulfilled: list[Order] = field(default_factory=list)
    next_id: int = 0

    def place(self, city: int, product: int, quantity: int, tick: int, reward: float) -> Order:
        order = Order(id=self.next_id, city=city, product=product,
                      quantity=quantity, placed_tick=tick, reward=reward)
        self.next_id += 1
        self.pending.append(order)
        return order

    def fulfil(self, order_id: int, agent_id: int, tick: int) -> Order | None:
        # remove from pending, set fulfilled fields, append to fulfilled
        ...


@dataclass(slots=True)
class ReorderPolicy:
    """(s, S) policy per (city, product)."""
    s: dict[tuple[int, int], int]  # reorder point
    S: dict[tuple[int, int], int]  # order-up-to level
    base_reward: float = 5.0

    def evaluate(self, market: object, mempool: LogisticsMempool, tick: int) -> int:
        """Per-tick: for each (city, product), if inventory[p] < s, place order."""
        placed = 0
        for (city, product), s_val in self.s.items():
            inv = market.markets[city].inventory.get(product, 0)
            outstanding = sum(
                o.quantity for o in mempool.pending
                if o.city == city and o.product == product
            )
            if inv + outstanding < s_val:
                qty = self.S[(city, product)] - inv - outstanding
                if qty > 0:
                    # Reward proportional to urgency (lower inv = higher reward).
                    urgency = 1.0 - (inv / max(s_val, 1))
                    reward = self.base_reward * (1.0 + urgency)
                    mempool.place(city, product, qty, tick, reward)
                    placed += 1
        return placed
```

**Modify** `packages/core/penumbra_core/economy.py`:
- Add `cargo_constraints: CargoConstraints | None` field to `Market`.
- In `settle_arrivals`, before BUY: check `cargo_constraints.available(...)`
  and cap `qty` accordingly.
- Add `Market.tick_logistics(demand_model, policy, mempool, tick)` that
  runs demand consumption + reorder evaluation in addition to the
  existing produce → reprice → settle.

**New analytics consumers** in `dashboard_pipeline.py`:

```python
@dataclass(slots=True)
class FillRateReport:
    overall_fill_rate: float       # 0..1
    per_product_fill_rate: tuple[tuple[int, float], ...]
    total_stockouts: int
    backlog_total: int
    n_samples: int

@dataclass(slots=True)
class InventoryHealthReport:
    per_city_per_product_inventory: tuple[tuple[int, int, int, int], ...]
    # (city, product, current_inventory, days_until_stockout_at_current_demand)
    holding_cost_total: float
    stockout_cost_total: float

@dataclass(slots=True)
class OrderBookReport:
    pending_count: int
    pending_orders: tuple[Order, ...]
    fulfilled_count: int
    median_lead_time_ticks: float
    p95_lead_time_ticks: float
```

Wire these into `DashboardPipeline.cadences` (5-10s cadence is fine; the
data doesn't change as fast as ticks).

**New API endpoints** in `packages/transport/penumbra_transport/api.py`:

| Method | Path | Returns |
|---|---|---|
| GET | `/logistics/fill-rate` | overall + per-product fill rate, backlog |
| GET | `/logistics/inventory-health` | per-city-per-product stock + days-of-supply |
| GET | `/logistics/orders` | pending + last N fulfilled orders + lead time stats |
| GET | `/logistics/reorder-policy` | current (s, S) per (city, product) |
| POST | `/logistics/reorder-policy` | mutate (s, S) live, like reward shaping |
| GET | `/logistics/capacity` | per-agent cargo capacity + utilization |

**New frontend tiles** in `apps/web/src/charts/`:

1. `FillRateChart.tsx` — overall fill rate as headline + per-product bars
2. `InventoryHealthChart.tsx` — heatmap: rows = products, cols = cities,
   cell color = days-of-supply (green = healthy, red = stockout imminent)
3. `OrderBookChart.tsx` — pending orders table + lead time histogram
4. `ReorderPolicyChart.tsx` — live (s, S) sliders per (city, product)
   focus group (pick 5 city-product pairs to tune)
5. `CargoUtilizationChart.tsx` — per-agent cargo usage bars

**Tests** in `packages/core/tests/test_logistics.py`:

- `test_cargo_capacity_caps_purchases` — agent at capacity can't buy more
- `test_demand_consumption_depletes_inventory` — N ticks of demand_rate=1
  reduces inventory by N (until stockout)
- `test_reorder_policy_triggers_order_when_below_s` — drop inventory
  below s, assert order placed
- `test_reorder_policy_no_duplicate_orders` — outstanding orders count
  toward decision, no double-ordering
- `test_fill_rate_computed_correctly` — controlled scenario where
  served/requested ratio is known a priori
- `test_lead_time_stats_match_recorded_orders` — fulfil N orders with
  known timestamps, assert median + p95

**Acceptance criteria (Tier 1)**:
- All 6 new endpoints respond 200 with non-empty `available: true`.
- 5 new tiles populate within 5s of dashboard open.
- Existing 326 tests still pass.
- 8 new tests cover the logistics primitives.
- No measurable regression in tick throughput (>9 Hz at default config).

---

### Tier 2 — OR optimization benchmark (~3-4h)

**Dependency**: `ortools` (Google's OR-Tools, ~80MB wheel).

**New file**: `packages/core/penumbra_core/vrp.py`

```python
"""OR-Tools VRP solver as centralized-planner benchmark.

Concept taught: the VRP solver knows EVERYTHING — all orders, all
distances, all capacities. A learned MAPPO policy makes DECENTRALIZED
decisions with only local observation. The optimality gap measures
how much we lose to decentralization.
"""

from ortools.constraint_solver import pywrapcp, routing_enums_pb2


@dataclass(slots=True)
class VRPSolution:
    routes_per_vehicle: tuple[tuple[int, ...], ...]
    total_distance: float
    n_orders_served: int
    n_orders_unserved: int
    compute_time_ms: float


def solve_vrp(
    distance_matrix: list[list[int]],
    demands: list[int],        # per-stop demand (order quantity)
    vehicle_capacities: list[int],
    depots: list[int],         # one per vehicle
    time_limit_ms: int = 5000,
) -> VRPSolution:
    """Solve capacitated VRP with multi-depot + time limit."""
    ...
```

**New endpoint** `/learning/vrp-optimal`:
- Takes current pending orders + agent positions + capacities
- Builds distance matrix from arena
- Calls `solve_vrp` (in `asyncio.to_thread` since it can take seconds)
- Returns optimal routes + total distance
- Cached per (set of pending orders) so repeated polls are fast

**New endpoint** `/learning/optimality-gap`:
- Returns `(mappo_total_distance - vrp_total_distance) / vrp_total_distance`
- Plus history over time

**New tile** `VRPComparisonChart.tsx`:
- Side-by-side: MAPPO actual routes (cyan) vs VRP optimal (ember)
- Headline: optimality gap %
- Time series of gap over last N ticks

**Tests**:
- `test_vrp_solver_with_known_optimal` — trivial 2-vehicle 4-order TSP
  with hand-computed optimum
- `test_optimality_gap_zero_for_optimal_routes` — feed VRP solution as
  agent moves, gap should be 0

**Acceptance**:
- VRP solver returns within 5s for 50-node × 20-order × 10-vehicle problem
- Optimality gap is meaningful (5-50% range typical for untrained MAPPO)
- Live update on dashboard within 10s of policy step

---

### Tier 3 — Multi-echelon supply chain (~5-6h)

**Conceptual change**: partition the 50 nodes into roles:
- 5 suppliers (produce raw goods at zero cost)
- 15 distributors (intermediate warehouses)
- 30 retailers (face end-customer demand)

Each level's orders propagate upstream. Distributors order from
suppliers when their stock drops; retailers order from distributors;
end-customer demand drives the whole chain.

**New file**: `packages/core/penumbra_core/supply_chain.py`

```python
@dataclass(slots=True)
class Echelon:
    nodes: tuple[int, ...]
    upstream: Echelon | None  # None for suppliers
    downstream: Echelon | None  # None for retailers


@dataclass(slots=True)
class BullwhipMeasurement:
    """Variance amplification per echelon over a rolling window."""
    variance_at_demand: float       # variance of end-customer demand
    variance_per_echelon: tuple[float, ...]  # one per echelon, from retailer to supplier
    bullwhip_ratio_per_echelon: tuple[float, ...]  # variance[e] / variance[demand]
    window_ticks: int


def measure_bullwhip(
    order_history: dict[Echelon, list[int]],
    demand_history: list[int],
    window: int = 200,
) -> BullwhipMeasurement:
    """Compute classical Forrester bullwhip ratio per echelon."""
    ...
```

**New analytics consumer** in `dashboard_pipeline.py`:

```python
@dataclass(slots=True)
class BullwhipReport:
    measurement: BullwhipMeasurement
    plot_data: tuple[tuple[str, tuple[float, ...]], ...]
    # (echelon_name, last_N_orders) — for the spaghetti-plot frontend
```

**New endpoints**:
- `/logistics/bullwhip` — current ratio + per-echelon series
- `/logistics/supply-chain-topology` — partition + edge counts

**New tiles**:
- `BullwhipChart.tsx` — variance ratio bar per echelon (1.0 = no amplification,
  > 1 = bullwhip present); spaghetti plot of order series per echelon
- `SupplyChainTopologyChart.tsx` — color the arena 2D graph by echelon role

**Tests**:
- `test_bullwhip_zero_for_constant_demand` — flat demand → ratio = 1
- `test_bullwhip_amplifies_with_lead_time` — longer lead time → higher ratio
- `test_safety_stock_reduces_stockouts_at_cost_of_holding`

**Acceptance**:
- Three echelons visible on dashboard, color-coded by role
- Bullwhip ratio computed and displayed
- Stockout rate decreases when safety_stock increases (classic tradeoff
  curve visible in the chart)

---

### Tier 4 — Advanced (~10h+)

Pick from this menu based on user interest:

#### 4.1 Multi-modal transport
- Agent subtypes: walker (cap 5, speed 1), horse (cap 20, speed 0.5),
  caravan (cap 100, speed 0.2)
- Edge weight × agent_speed = actual travel time
- Optimization: which mode for which corridor?

#### 4.2 Cross-docking
- A node type that doesn't STORE: incoming goods immediately rerouted
- Reduces holding cost but increases routing complexity
- Visible in the analytics: cross-dock nodes have inventory ≈ 0
  but high throughput

#### 4.3 Risk pooling (centralization)
- Run two simulations side-by-side: N decentralized warehouses vs 1
  centralized warehouse with the same total demand
- Show: centralized has LOWER variance of demand seen (variance of sum
  < sum of variances when correlations are low)
- Classic pedagogical demo of why hub-and-spoke beats fully meshed
  for many product categories

#### 4.4 Stochastic lead times
- Edge travel time drawn from a distribution, not deterministic
- Safety stock formula s = z_alpha · σ_demand · √(lead_time)
  becomes observable
- Robust optimization: pick (s, S) that minimizes worst-case cost
  over a scenario tree

#### 4.5 LP relaxation + min-cost flow
- For each tick: compute the optimal LP allocation (assuming continuous
  cargo) using `scipy.optimize.linprog`
- Compare integer (real) vs LP (relaxed) solution
- Pedagogical: the integrality gap on logistics LPs is typically small

#### 4.6 Demand forecasting integration
- Use the existing ARIMA module on the demand history per product
- (s, S) policies parameterized by forecast σ instead of historical σ
- Show: better forecasts → lower safety stock → lower holding cost
  at same service level

---

## 5. New configuration / environment

`packages/core/penumbra_core/economy.py` already has tunable constants;
add a logistics-specific block:

```python
# ── Logistics tuning ──────────────────────────────────────────
_DEFAULT_CARGO_CAPACITY: Final[int] = 20
_DEFAULT_DEMAND_RATE_PER_PRODUCT: Final[float] = 0.05
_DEFAULT_HOLDING_COST_PER_UNIT_PER_TICK: Final[float] = 0.001
_DEFAULT_STOCKOUT_COST_PER_UNIT_PER_TICK: Final[float] = 0.05
_DEFAULT_REORDER_POINT_FRACTION: Final[float] = 0.3   # s = 0.3 * max_inventory
_DEFAULT_ORDER_UP_TO_FRACTION: Final[float] = 0.8     # S = 0.8 * max_inventory
```

Environment variables for CLI / docker compose:
- `PENUMBRA_LOGISTICS_ENABLED={0,1}` — gate Tier 1 features (default 0
  during stabilization)
- `PENUMBRA_SUPPLY_CHAIN_ENABLED={0,1}` — gate Tier 3
- `PENUMBRA_VRP_TIME_LIMIT_MS=5000` — OR-Tools solver budget

## 6. Memory + performance impact

Estimated overhead per tick at Tier 1:
- Demand consumption: 50 cities × 10 stocked products × O(1) = 500 ops
- Reorder policy check: same = 500 ops
- Plus 1 Order allocation per reorder (rare, < 10 per tick)
- **Net: < 1ms additional CPU per tick**, no memory growth

Tier 2 (VRP solver): runs OFF the tick loop, asyncio.to_thread, cached.
Up to 5s of CPU per solve, but at most once per ~30s (cache).

Tier 3 (bullwhip measurement): rolling 200-tick window, ~10ms compute
every 5s cadence.

**M4 budget impact**: < 100MB additional RSS at all tiers combined.
Within the existing 8GB target.

## 7. Tests we'd add

| Tier | Test file | Count |
|---|---|---|
| 1 | `packages/core/tests/test_logistics.py` | 8 |
| 1 | `packages/analytics/tests/test_logistics_consumers.py` | 4 |
| 2 | `packages/core/tests/test_vrp.py` | 4 |
| 3 | `packages/core/tests/test_supply_chain.py` | 6 |
| 3 | `packages/analytics/tests/test_bullwhip.py` | 3 |
| 4 | Per-feature, ~3 each |
| **Total Tier 1-3** | | **25** |

Property-based tests with `hypothesis` for invariants:
- Cargo capacity invariant: agent inventory total ≤ capacity, always
- Money conservation: still holds after demand consumption
- Order monotonicity: fulfilled count never decreases
- Bullwhip invariant: ratio ≥ 1 for any non-degenerate demand process

## 8. Acceptance criteria (whole layer)

Tier 1 done when:
- [ ] 8 logistics tests pass
- [ ] 5 dashboard tiles populate live
- [ ] Backend regression: 302/302 existing tests still pass
- [ ] Tick throughput >= 9 Hz under load
- [ ] CLAUDE.md + ROADMAP.md updated
- [ ] One PR / one tag `logistics-tier-1`

Tier 2-4 done when (each):
- Independent PR with tests + tiles + docs
- Visible KPI improvement or new pedagogical signal demonstrated
- `crypto-auditor` review not needed (logistics doesn't touch crypto)

## 9. What's explicitly OUT of scope

- Real ERP integration (SAP, Oracle, NetSuite)
- Currency exchange / FX (single-currency economy)
- Carbon-cost / sustainability KPIs (could add as Tier 5)
- Real-world logistics network data import
- Multi-tenant / multi-organization
- Real-time WebSocket order streaming (poll cadence is fine)
- Mobile / responsive layouts

## 10. Pedagogical / business positioning

Where each Tier maps to a target audience:

| Tier | Audience | Concepts taught |
|---|---|---|
| 1 | Industrial engineering undergrads | Capacity, demand, fill rate, reorder policy |
| 2 | OR practitioners + MBA OM | VRP, optimality gap, learned vs optimal |
| 3 | Supply chain managers | Bullwhip, safety stock, multi-echelon, JIT vs JIC |
| 4 | Research / consulting | Robust optimization, LP relaxation, risk pooling |

For Edu B2B: Tier 1+2 alone gives a 4-hour workshop module. Tier 3
adds a second workshop. Tier 4 is post-workshop deep-dive.

For OSS: Tier 1 alone unlocks SCM-research citation potential. The
"50 agents on a graph with crypto AND logistics" combination is
unique in the literature.

## 11. References

For implementers and for the `concept_taught` docstrings:

- Forrester, Jay W. *Industrial Dynamics*. MIT Press, 1961.
  (Original bullwhip work.)
- Lee, Padmanabhan, Whang. "The Bullwhip Effect in Supply Chains."
  *Sloan Management Review*, 1997.
- Toth, Vigo (eds). *Vehicle Routing: Problems, Methods, and Applications*,
  2nd ed. SIAM, 2014. (VRP canonical reference.)
- Snyder, Shen. *Fundamentals of Supply Chain Theory*. Wiley, 2019.
- Google OR-Tools docs: https://developers.google.com/optimization/routing
- Silver, Pyke, Thomas. *Inventory and Production Management in Supply
  Chains*, 4th ed. CRC Press, 2017. (s, S, EOQ, multi-echelon.)

## 12. Implementation order (recommended)

1. Read this document end-to-end.
2. Open `packages/core/penumbra_core/economy.py` and `dashboard_pipeline.py`
   to refresh memory of the existing `Market` / `Trade` types.
3. Implement Tier 1 in this order:
   1. `logistics.py` module (no integration yet — pure code + unit tests).
   2. `economy.py` extension (cargo capacity + hook for demand model).
   3. Pipeline consumers (`fill_rate`, `inventory_health`, `order_book`).
   4. API endpoints.
   5. Frontend charts.
   6. Tour overlay step + ANALYTICS_PANEL tiles.
   7. ROADMAP + CLAUDE.md update.
4. Verify full gate (302 → 310 backend tests; 24 → 24 vitest; biome
   pyright ruff clean).
5. Commit as `feat(logistics): tier 1 — cargo + demand + (s, S) + KPIs`,
   tag `logistics-tier-1`.
6. Show user the 5 new tiles via screenshot.
7. Decide Tier 2-4 sequencing with the user.

---

**End of plan.** All design decisions in this document are intentional;
deviations should be deliberate. When implementing, link back to this
document in commit messages so future readers can find the rationale.
