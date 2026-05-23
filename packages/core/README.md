# penumbra-core

Pure domain. No I/O. The integration seam where every Penumbra pillar
ultimately meets on each simulation tick.

## Concept taught

- **`rng.py`** — centralised reproducibility. One env-seeded source fans out
  to `random`, `numpy`, `torch`, `jax`. *Concept:* multi-library RNG hygiene.
- **`arena.py`** — graph world with Ornstein-Uhlenbeck edge costs, migrating
  goals, weather. *Concept:* SDE-driven graph dynamics → no static shortest
  path.
- **`agent.py`, `match.py`, `simulation.py`** — agents, episodes, the
  perpetual tick loop. *Concept:* an "episode" is an artificial boundary on
  a continuous-time process; the simulation persists agents and stats
  across them.
- **`economy.py`** — the closed two-sided market. Wallets +
  city-state (stocked products, inventory, dynamic ask price, treasury);
  per-tick `Market.tick()` runs produce → reprice → settle arrivals
  (sell first, then buy). Money is conserved; inflation emerges from
  supply/demand pressure on a FIXED money base. *Concept:* how a
  macro-level price index can rise without monetary expansion.

## Micro-experiments

- Seed the RNG to two values, run 1000 ticks each, diff the agent
  trajectories. Identical seeds → identical trajectories.
- Halve the OU mean-reversion in `arena.py`; observe how edge-cost volatility
  affects coalition formation.

## Public API

```python
from penumbra_core.rng import bootstrap, run_record
from penumbra_core.arena import Arena, ArenaConfig
from penumbra_core.agent import Agent
from penumbra_core.match import Match
from penumbra_core.simulation import Simulation
from penumbra_core.economy import (
    Market, Wallet, MarketState, Trade,
    PRODUCT_CATALOG, PRODUCT_CATEGORIES,
)
from penumbra_core.logistics import (
    CargoConstraints, DemandModel, LogisticsMempool,
    Order, ReorderPolicy,
    FillRateReport, InventoryHealthReport, OrderBookReport,
    CargoUtilizationReport, DispatchReport,
    compute_fill_rate, compute_inventory_health, compute_order_book,
    compute_cargo_utilization, compute_dispatch_report,
    assign_carriers,
)
from penumbra_core.logistics_or import (
    VRPInstance, VRPOrder, VRPSolution,
    solve_greedy_nearest_neighbor, solve_two_opt, solve_or_tools,
    build_arena_distance_matrix,
)
from penumbra_core.logistics_echelon import (
    SupplyNode, EchelonNetwork,
    EchelonReport, compute_echelon_report,
    step as echelon_step,
    bullwhip_ratio,
)
```

## Phase 2.5 additions (logistics layer)

- **logistics.py** — `Concept taught:` how OR-style supply-chain
  operations (cargo capacity, demand curves, (s,S) reorder, carrier
  dispatch) emerge from primitive nodes + KPIs.
- **logistics_or.py** — `Concept taught:` Vehicle Routing Problem
  solvers (greedy nearest-neighbour, 2-opt local search, OR-Tools
  CP-SAT). Used as an optimisation reference against MAPPO + heuristic
  policies.
- **logistics_echelon.py** — `Concept taught:` multi-echelon
  inventory propagation (supplier → distributor → city), lead-time
  delays, the bullwhip effect (variance amplification upstream).
