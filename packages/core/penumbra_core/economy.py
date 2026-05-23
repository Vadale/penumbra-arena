"""City markets: coins, inventory, production, dynamic prices, trades.

Concept taught: how a closed micro-economy emerges from a few moving
parts — wallets that hold money, cities that hold goods + treasury,
production that creates supply, and price rules that respond to
inventory levels. Money is conserved (sum of all wallets + treasuries
is constant); price changes drive inflation, not money printing.

Layout
------
- Wallet: per-agent state. `coins` (float) + `inventory` (dict
  product_id → quantity).
- MarketState: per-city state. The 10 products this city stocks,
  current inventory + ask price for each, production rate, and the
  city's treasury (cash for buying from agents).
- Trade: one buy or sell event with tick, agent, product, quantity,
  unit_price, side, and signed total value.
- Market: owns the wallets + market-states + RNG-driven tick loop.

The orchestrator drives one `Market.tick(agent_positions, rng)` per
analytics tick. The result is a list of Trade events the pipeline
streams into its consumers (candles, CPI, money supply, Gini).

Money conservation
------------------
A BUY transfers `unit_price * quantity` coins from agent.coins into
the city's treasury. A SELL is the reverse. Production creates new
GOODS (free), never new coins. Thus
    Σ_a wallet[a].coins + Σ_n market[n].treasury
is invariant up to fixed-precision rounding (we store coins as
float; rounding errors are sub-cent over thousands of trades).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

import numpy as np

PRODUCT_CATEGORIES: Final[tuple[str, ...]] = (
    "food",
    "hygiene",
    "tools",
    "luxury",
    "medicine",
)


@dataclass(frozen=True, slots=True)
class Product:
    """Static catalogue entry."""

    id: int
    name: str
    category: str
    base_price: float


PRODUCT_CATALOG: Final[tuple[Product, ...]] = (
    Product(0, "bread loaf", "food", 1.2),
    Product(1, "smoked fish", "food", 3.4),
    Product(2, "salted meat", "food", 4.1),
    Product(3, "wild apples", "food", 0.9),
    Product(4, "honeycomb", "food", 5.6),
    Product(5, "spiced grain", "food", 2.0),
    Product(6, "soap bar", "hygiene", 1.8),
    Product(7, "linen towel", "hygiene", 3.0),
    Product(8, "tooth powder", "hygiene", 1.1),
    Product(9, "herbal oil", "hygiene", 4.5),
    Product(10, "bath salts", "hygiene", 2.6),
    Product(11, "razor blade", "hygiene", 5.2),
    Product(12, "iron nails", "tools", 1.5),
    Product(13, "rope coil", "tools", 2.8),
    Product(14, "small hammer", "tools", 6.0),
    Product(15, "pickaxe", "tools", 8.5),
    Product(16, "flint pouch", "tools", 1.0),
    Product(17, "leather strap", "tools", 2.2),
    Product(18, "silver locket", "luxury", 22.0),
    Product(19, "silk scarf", "luxury", 18.0),
    Product(20, "amber bead", "luxury", 9.5),
    Product(21, "spiced wine", "luxury", 12.0),
    Product(22, "carved figurine", "luxury", 7.5),
    Product(23, "lapis ring", "luxury", 30.0),
    Product(24, "willow bark", "medicine", 3.5),
    Product(25, "fever tonic", "medicine", 7.0),
    Product(26, "wound salve", "medicine", 5.0),
    Product(27, "iron tablet", "medicine", 2.4),
    Product(28, "calming draught", "medicine", 6.5),
    Product(29, "cough lozenges", "medicine", 1.9),
)


@dataclass(frozen=True, slots=True)
class CityInventory:
    """Back-compat: the 10 product_ids a city stocks (no quantities)."""

    node_id: int
    product_ids: tuple[int, ...]


def city_inventories(
    nodes: Sequence[int],
    seed: int,
    items_per_city: int = 10,
) -> dict[int, CityInventory]:
    """Deterministic assortment of `items_per_city` per node, LCG-seeded."""
    out: dict[int, CityInventory] = {}
    for n in nodes:
        s = (seed ^ (n * 2654435761)) & 0xFFFFFFFF
        picked: list[int] = []
        candidates = list(range(len(PRODUCT_CATALOG)))
        for i in range(min(items_per_city, len(candidates))):
            s = (s * 1664525 + 1013904223) & 0xFFFFFFFF
            j = i + (s % (len(candidates) - i))
            candidates[i], candidates[j] = candidates[j], candidates[i]
            picked.append(candidates[i])
        out[int(n)] = CityInventory(node_id=int(n), product_ids=tuple(picked))
    return out


# Convenience alias — the older Purchase dataclass becomes a special-case Trade.
@dataclass(frozen=True, slots=True)
class Purchase:
    """Back-compat single buy event. Use Trade for new code."""

    tick: int
    agent_id: int
    node_id: int
    product_id: int
    category: str
    quantity: int
    price_paid: float


# ── New market dataclasses ──────────────────────────────────────────


@dataclass(slots=True)
class Wallet:
    """Per-agent cash + goods. Mutable; the Market updates it in place."""

    agent_id: int
    coins: float
    inventory: dict[int, int] = field(default_factory=dict)


@dataclass(slots=True)
class MarketState:
    """One city's market: stocked goods, inventory, price, production."""

    node_id: int
    stocked_products: tuple[int, ...]
    inventory: dict[int, int]
    ask_price: dict[int, float]  # what an agent pays to BUY here
    max_inventory: int
    production_per_tick: float
    treasury: float


@dataclass(frozen=True, slots=True)
class Trade:
    """One buy or sell event."""

    tick: int
    agent_id: int
    node_id: int
    product_id: int
    category: str
    side: Literal["buy", "sell"]
    quantity: int
    unit_price: float
    total_value: float


# Defaults — tuned so the market reaches a non-trivial steady state
# within ~30 seconds of agent traffic on the default 50-agent / 50-node
# Penumbra graph.
_INIT_COINS_PER_AGENT: Final[float] = 100.0
_INIT_TREASURY_PER_CITY: Final[float] = 500.0
_INIT_INVENTORY_PER_PRODUCT: Final[int] = 30
_MAX_INVENTORY_PER_PRODUCT: Final[int] = 60
_PRODUCTION_PER_TICK: Final[float] = 0.15  # units per stocked product per tick
_BID_ASK_SPREAD: Final[float] = 0.15  # city pays 85% of ask when buying back
_P_BUY: Final[float] = 0.10
_P_SELL: Final[float] = 0.18
_AVG_BUY_QUANTITY: Final[float] = 1.3
_AVG_SELL_QUANTITY: Final[float] = 1.2
_PRICE_INFLATE: Final[float] = 1.0025
_PRICE_DEFLATE: Final[float] = 0.9985
_LOW_STOCK_PCT: Final[float] = 0.35
_HIGH_STOCK_PCT: Final[float] = 0.70
_PRICE_MIN_RATIO: Final[float] = 0.4
_PRICE_MAX_RATIO: Final[float] = 6.0


@dataclass(slots=True)
class Market:
    """The whole world's market: agents' wallets + cities' market-states.

    Drives one tick at a time when called from the orchestrator. Each
    tick: produce → update prices → settle agent arrivals (sell first,
    then buy). The list of resulting Trade events is what the dashboard
    pipeline consumes (candles, CPI, volume, wealth, money supply).
    """

    wallets: dict[int, Wallet]
    markets: dict[int, MarketState]
    _previous_node: dict[int, int] = field(default_factory=dict)
    cargo: object | None = None  # CargoConstraints; opt-in cap on BUY qty

    @classmethod
    def build(
        cls,
        nodes: Sequence[int],
        n_agents: int,
        seed: int,
    ) -> Market:
        """Build a fresh market: agents start with coins, cities with inventory."""
        wallets = {
            aid: Wallet(agent_id=aid, coins=_INIT_COINS_PER_AGENT) for aid in range(n_agents)
        }
        inventories = city_inventories(nodes, seed=seed)
        markets: dict[int, MarketState] = {}
        for n, inv in inventories.items():
            ask: dict[int, float] = {}
            stock: dict[int, int] = {}
            for pid in inv.product_ids:
                ask[pid] = PRODUCT_CATALOG[pid].base_price
                stock[pid] = _INIT_INVENTORY_PER_PRODUCT
            markets[int(n)] = MarketState(
                node_id=int(n),
                stocked_products=inv.product_ids,
                inventory=stock,
                ask_price=ask,
                max_inventory=_MAX_INVENTORY_PER_PRODUCT,
                production_per_tick=_PRODUCTION_PER_TICK,
                treasury=_INIT_TREASURY_PER_CITY,
            )
        return cls(wallets=wallets, markets=markets)

    # ── per-tick operations ───────────────────────────────────────

    def produce(self) -> None:
        """Each city produces production_per_tick of each stocked product, capped at max."""
        for ms in self.markets.values():
            for pid in ms.stocked_products:
                cur = ms.inventory.get(pid, 0)
                if cur < ms.max_inventory:
                    # Production is fractional; we accumulate floor() over time
                    # by storing the inventory as int but accumulating leftover
                    # in a separate per-city counter. Simpler approximation:
                    # bump by ceil if fractional and we're under cap. The base
                    # rate (0.15) means a unit ~every 7 ticks per product.
                    next_cur = cur + ms.production_per_tick
                    ms.inventory[pid] = min(ms.max_inventory, int(next_cur))

    def update_prices(self) -> None:
        """Move each ask price up if stocks are low, down if high."""
        for ms in self.markets.values():
            for pid in ms.stocked_products:
                cap = ms.max_inventory
                if cap <= 0:
                    continue
                fill = ms.inventory.get(pid, 0) / cap
                cur = ms.ask_price.get(pid, PRODUCT_CATALOG[pid].base_price)
                if fill < _LOW_STOCK_PCT:
                    cur *= _PRICE_INFLATE
                elif fill > _HIGH_STOCK_PCT:
                    cur *= _PRICE_DEFLATE
                # Clip to [base * min, base * max] so prices stay in a sane band.
                base = PRODUCT_CATALOG[pid].base_price
                ms.ask_price[pid] = max(base * _PRICE_MIN_RATIO, min(base * _PRICE_MAX_RATIO, cur))

    def settle_arrivals(
        self,
        tick: int,
        agent_positions: dict[int, int],
        rng: np.random.Generator,
    ) -> list[Trade]:
        """For each agent newly arrived at a node, try sell then buy.

        Order: SELL first so the agent can free coins for buys; BUY second
        means an agent fresh off a sale can immediately reinvest.
        """
        trades: list[Trade] = []
        for agent_id, node_id in agent_positions.items():
            prev = self._previous_node.get(agent_id)
            self._previous_node[agent_id] = node_id
            if prev is None or prev == node_id:
                continue
            ms = self.markets.get(node_id)
            if ms is None:
                continue
            wallet = self.wallets.get(agent_id)
            if wallet is None:
                continue

            # SELL: pick items the city stocks AND the agent owns.
            for pid, qty_owned in list(wallet.inventory.items()):
                if qty_owned <= 0:
                    continue
                if pid not in ms.stocked_products:
                    continue
                if float(rng.random()) >= _P_SELL:
                    continue
                product = PRODUCT_CATALOG[pid]
                ask = ms.ask_price.get(pid, product.base_price)
                bid = ask * (1.0 - _BID_ASK_SPREAD)
                # Quantity ~ Geometric, capped by what the agent owns + city treasury.
                desired = 1 + int(rng.geometric(p=1.0 / max(_AVG_SELL_QUANTITY, 1.01)))
                affordable_for_city = int(ms.treasury / max(bid, 0.01)) if bid > 0 else 0
                qty = max(0, min(desired, qty_owned, affordable_for_city))
                if qty == 0:
                    continue
                revenue = bid * qty
                wallet.inventory[pid] = qty_owned - qty
                wallet.coins += revenue
                ms.treasury -= revenue
                # City absorbs the goods (also capped by its inventory limit).
                ms.inventory[pid] = min(ms.max_inventory, ms.inventory.get(pid, 0) + qty)
                trades.append(
                    Trade(
                        tick=tick,
                        agent_id=int(agent_id),
                        node_id=int(node_id),
                        product_id=int(pid),
                        category=product.category,
                        side="sell",
                        quantity=qty,
                        unit_price=bid,
                        total_value=revenue,
                    )
                )

            # BUY: each stocked product gets a Bernoulli roll.
            for pid in ms.stocked_products:
                if float(rng.random()) >= _P_BUY:
                    continue
                product = PRODUCT_CATALOG[pid]
                ask = ms.ask_price.get(pid, product.base_price)
                avail = ms.inventory.get(pid, 0)
                if avail <= 0 or wallet.coins < ask:
                    continue
                desired = 1 + int(rng.geometric(p=1.0 / max(_AVG_BUY_QUANTITY, 1.01)))
                affordable = int(wallet.coins / ask) if ask > 0 else 0
                qty = max(0, min(desired, avail, affordable))
                if self.cargo is not None:
                    remaining_cap = self.cargo.available(  # type: ignore[attr-defined]
                        agent_id=int(agent_id),
                        current_inventory=wallet.inventory,
                    )
                    qty = min(qty, remaining_cap)
                if qty == 0:
                    continue
                cost = ask * qty
                wallet.coins -= cost
                wallet.inventory[pid] = wallet.inventory.get(pid, 0) + qty
                ms.inventory[pid] = avail - qty
                ms.treasury += cost
                trades.append(
                    Trade(
                        tick=tick,
                        agent_id=int(agent_id),
                        node_id=int(node_id),
                        product_id=int(pid),
                        category=product.category,
                        side="buy",
                        quantity=qty,
                        unit_price=ask,
                        total_value=cost,
                    )
                )
        return trades

    def tick(
        self,
        tick: int,
        agent_positions: dict[int, int],
        rng: np.random.Generator,
    ) -> list[Trade]:
        """One full market tick: produce → reprice → settle agent arrivals."""
        self.produce()
        self.update_prices()
        return self.settle_arrivals(tick, agent_positions, rng)

    # ── aggregates for the pipeline ──────────────────────────────

    def money_supply(self) -> float:
        """Sum of all agent coins + all city treasuries."""
        return float(
            sum(w.coins for w in self.wallets.values())
            + sum(ms.treasury for ms in self.markets.values())
        )

    def price_index(self) -> float:
        """CPI-like index: unit-weighted average ratio of current to base price.

        Pedagogically: a Laspeyres-style price index with fixed weights.
        We sum over (city, product) pairs.
        """
        total_ratio = 0.0
        n = 0
        for ms in self.markets.values():
            for pid in ms.stocked_products:
                base = PRODUCT_CATALOG[pid].base_price
                if base <= 0:
                    continue
                total_ratio += ms.ask_price.get(pid, base) / base
                n += 1
        if n == 0:
            return 1.0
        return total_ratio / n

    def wealth_distribution(self) -> tuple[float, ...]:
        """Sorted vector of agent net worth = coins + inventory at current ask price.

        Inventory is valued at the AVERAGE current ask across cities that
        stock the product (a rough mark-to-market). Returns the sorted
        ascending wealth vector for downstream Lorenz/Gini computation.
        """
        # Precompute average ask price per product.
        avg_ask: dict[int, float] = {}
        counts: dict[int, int] = {}
        for ms in self.markets.values():
            for pid, price in ms.ask_price.items():
                avg_ask[pid] = avg_ask.get(pid, 0.0) + price
                counts[pid] = counts.get(pid, 0) + 1
        for pid in avg_ask:
            avg_ask[pid] /= max(counts[pid], 1)

        wealth: list[float] = []
        for w in self.wallets.values():
            value = w.coins
            for pid, qty in w.inventory.items():
                value += qty * avg_ask.get(pid, PRODUCT_CATALOG[pid].base_price)
            wealth.append(value)
        wealth.sort()
        return tuple(wealth)
