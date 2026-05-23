/**
 * Logistics order-book tile.
 *
 * Pending / fulfilled order counts + lead-time stats + a sample of
 * the pending order book.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Payload {
  available: boolean;
  n_pending?: number;
  n_fulfilled?: number;
  median_lead_time_ticks?: number;
  p95_lead_time_ticks?: number;
  pending_sample?: Array<[number, number, number, number, number, number]>;
}

export function LogisticsOrdersChart() {
  const [data, setData] = useState<Payload | null>(null);
  useEffect(() => {
    let cancel = false;
    const tick = async () => {
      try {
        const res = await fetch("/logistics/orders");
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
        no order data yet
      </div>
    );
  }
  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="pending" value={data.n_pending ?? 0} />
        <Stat label="fulfilled" value={data.n_fulfilled ?? 0} accent />
        <Stat label="median LT" value={data.median_lead_time_ticks ?? 0} digits={1} suffix="t" />
        <Stat label="p95 LT" value={data.p95_lead_time_ticks ?? 0} digits={1} suffix="t" />
      </div>
      <ul className="text-[10px] space-y-1">
        {(data.pending_sample ?? []).slice(0, 6).map((row) => {
          const [id, city, product, qty, placed, reward] = row;
          return (
            <li key={`o-${id}`}>
              #{id} · city {city} · product {product} · qty {qty} · placed @ t{placed} · reward{" "}
              {reward.toFixed(1)}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
