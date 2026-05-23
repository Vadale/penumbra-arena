/**
 * Inventory health tile.
 *
 * Renders n_stockouts, holding + stockout costs, and a short list
 * of the lowest-stock cells. Polled every 5s.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Payload {
  available: boolean;
  cells?: Array<[number, number, number, number]>;
  holding_cost_total?: number;
  stockout_cost_total?: number;
  n_stockouts?: number;
  n_cells_total?: number;
}

export function LogisticsInventoryHealthChart() {
  const [data, setData] = useState<Payload | null>(null);
  useEffect(() => {
    let cancel = false;
    const tick = async () => {
      try {
        const res = await fetch("/logistics/inventory-health");
        if (res.ok && !cancel) setData((await res.json()) as Payload);
      } catch {}
    };
    void tick();
    const h = window.setInterval(tick, 5000);
    return () => {
      cancel = true;
      window.clearInterval(h);
    };
  }, []);

  if (!data?.available) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        no inventory data yet
      </div>
    );
  }
  const lowest = (data.cells ?? [])
    .slice()
    .sort((a, b) => a[2] - b[2])
    .slice(0, 6);
  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="cells" value={data.n_cells_total ?? 0} />
        <Stat label="stockouts" value={data.n_stockouts ?? 0} ember={(data.n_stockouts ?? 0) > 0} />
        <Stat label="holding cost" value={data.holding_cost_total ?? 0} digits={2} />
      </div>
      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        Lowest-stock cells (city, product, inv / cap)
      </div>
      <ul className="text-[10px] space-y-1">
        {lowest.map(([city, product, inv, cap]) => (
          <li
            key={`${city}-${product}`}
            className={inv === 0 ? "text-[color:var(--color-penumbra-ember)]" : ""}
          >
            city {city} · product {product} · {inv}/{cap}
          </li>
        ))}
      </ul>
    </div>
  );
}
