"""Tiny city economy: each node sells 10 products, agents buy when they arrive.

Concept taught: tying a procedural-generation seed to a per-city
inventory + an event stream of purchases. Downstream this becomes
real data for the regression/logit/Granger/bayesian/PCA consumers,
so every chart in the dashboard sees a fresh, semantically rich
signal that's NOT just a function of the trajectory norm.

Catalogue
---------
30 fictional products in 5 categories: food, hygiene, tools, luxury,
medicine. Each has a base price. Per-city assortment of 10 is drawn
deterministically from the simulation seed + node id so the world's
shopping options are stable across reloads.

Purchase event
--------------
When an agent's previous_node != current_node, we treat the arrival
as a "visit" and roll a Bernoulli(p_buy) per item the city stocks;
if it fires, the agent buys a Geometric(1/avg_qty) quantity. Result
is exposed as a `Purchase` named tuple and accumulated by the
orchestrator into the dashboard pipeline's economy buffer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

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
    """A catalog entry. Stable across the simulation lifetime."""

    id: int
    name: str
    category: str
    base_price: float


# 30 products, ~6 per category. Names kept playful but consistent.
PRODUCT_CATALOG: Final[tuple[Product, ...]] = (
    # food
    Product(0, "bread loaf", "food", 1.2),
    Product(1, "smoked fish", "food", 3.4),
    Product(2, "salted meat", "food", 4.1),
    Product(3, "wild apples", "food", 0.9),
    Product(4, "honeycomb", "food", 5.6),
    Product(5, "spiced grain", "food", 2.0),
    # hygiene
    Product(6, "soap bar", "hygiene", 1.8),
    Product(7, "linen towel", "hygiene", 3.0),
    Product(8, "tooth powder", "hygiene", 1.1),
    Product(9, "herbal oil", "hygiene", 4.5),
    Product(10, "bath salts", "hygiene", 2.6),
    Product(11, "razor blade", "hygiene", 5.2),
    # tools
    Product(12, "iron nails", "tools", 1.5),
    Product(13, "rope coil", "tools", 2.8),
    Product(14, "small hammer", "tools", 6.0),
    Product(15, "pickaxe", "tools", 8.5),
    Product(16, "flint pouch", "tools", 1.0),
    Product(17, "leather strap", "tools", 2.2),
    # luxury
    Product(18, "silver locket", "luxury", 22.0),
    Product(19, "silk scarf", "luxury", 18.0),
    Product(20, "amber bead", "luxury", 9.5),
    Product(21, "spiced wine", "luxury", 12.0),
    Product(22, "carved figurine", "luxury", 7.5),
    Product(23, "lapis ring", "luxury", 30.0),
    # medicine
    Product(24, "willow bark", "medicine", 3.5),
    Product(25, "fever tonic", "medicine", 7.0),
    Product(26, "wound salve", "medicine", 5.0),
    Product(27, "iron tablet", "medicine", 2.4),
    Product(28, "calming draught", "medicine", 6.5),
    Product(29, "cough lozenges", "medicine", 1.9),
)


@dataclass(frozen=True, slots=True)
class CityInventory:
    """The 10 products a particular city stocks."""

    node_id: int
    product_ids: tuple[int, ...]


def city_inventories(
    nodes: Sequence[int],
    seed: int,
    items_per_city: int = 10,
) -> dict[int, CityInventory]:
    """Deterministic assortment of `items_per_city` per node.

    A simple LCG seeded by (seed XOR node_id) picks the items. Same
    inputs ⇒ same world economy across reloads.
    """
    out: dict[int, CityInventory] = {}
    for n in nodes:
        s = (seed ^ (n * 2654435761)) & 0xFFFFFFFF
        picked: list[int] = []
        candidates = list(range(len(PRODUCT_CATALOG)))
        # Fisher-Yates with seeded LCG.
        for i in range(min(items_per_city, len(candidates))):
            s = (s * 1664525 + 1013904223) & 0xFFFFFFFF
            j = i + (s % (len(candidates) - i))
            candidates[i], candidates[j] = candidates[j], candidates[i]
            picked.append(candidates[i])
        out[int(n)] = CityInventory(node_id=int(n), product_ids=tuple(picked))
    return out


@dataclass(frozen=True, slots=True)
class Purchase:
    """One agent's purchase event at a city (tick-precise)."""

    tick: int
    agent_id: int
    node_id: int
    product_id: int
    category: str
    quantity: int
    price_paid: float


@dataclass(slots=True)
class PurchaseClock:
    """Per-orchestrator state: tracks previous node per agent.

    Roll Bernoulli purchases when an agent's node changes.
    """

    inventories: dict[int, CityInventory]
    _previous: dict[int, int] = field(default_factory=dict)
    p_buy_per_item: float = 0.06
    avg_quantity: float = 1.5

    def settle_tick(
        self,
        tick: int,
        agent_positions: dict[int, int],
        rng: np.random.Generator,
    ) -> list[Purchase]:
        """Detect arrivals at cities and emit purchase events.

        `rng` is an `np.random.Generator` from `Seeded.numpy_for(...)`.
        Returns the list of purchases that fired this tick (may be empty).
        """
        events: list[Purchase] = []
        for agent_id, node_id in agent_positions.items():
            prev = self._previous.get(agent_id)
            self._previous[agent_id] = node_id
            if prev is None or prev == node_id:
                continue
            inventory = self.inventories.get(node_id)
            if inventory is None:
                continue
            # For each item in the city's assortment, Bernoulli(p_buy_per_item).
            for pid in inventory.product_ids:
                if float(rng.random()) >= self.p_buy_per_item:
                    continue
                product = PRODUCT_CATALOG[pid]
                # Quantity ~ Geometric with mean ~avg_quantity ⇒ p = 1 / avg.
                q = 1 + int(rng.geometric(p=1.0 / max(self.avg_quantity, 1.01)))
                events.append(
                    Purchase(
                        tick=tick,
                        agent_id=int(agent_id),
                        node_id=int(node_id),
                        product_id=int(pid),
                        category=product.category,
                        quantity=q,
                        price_paid=float(product.base_price * q),
                    )
                )
        return events
