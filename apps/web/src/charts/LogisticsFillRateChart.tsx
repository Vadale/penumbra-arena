/**
 * Logistics fill-rate tile.
 *
 * Surfaces the end-customer demand satisfaction ratio (served /
 * requested) and the per-product breakdown. Polled every 5s.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Payload {
  available: boolean;
  overall_fill_rate?: number;
  total_served?: number;
  total_requested?: number;
  total_backlog?: number;
  per_product?: Array<[number, number]>;
}

export function LogisticsFillRateChart() {
  const [data, setData] = useState<Payload | null>(null);

  useEffect(() => {
    let cancel = false;
    const tick = async () => {
      try {
        const res = await fetch("/logistics/fill-rate");
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
        no demand data yet
      </div>
    );
  }
  const rate = data.overall_fill_rate ?? 0;
  const isGood = rate >= 0.9;
  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat
          label="fill rate"
          value={rate * 100}
          accent={isGood}
          ember={!isGood}
          digits={1}
          suffix="%"
        />
        <Stat label="served" value={data.total_served ?? 0} />
        <Stat
          label="backlog"
          value={data.total_backlog ?? 0}
          ember={(data.total_backlog ?? 0) > 0}
        />
      </div>
      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        served / requested across all (city, product) pairs. Backlog accumulates when demand outruns
        inventory.
      </div>
    </div>
  );
}
