/**
 * Cargo capacity / utilisation tile.
 *
 * Mean utilisation across the fleet plus a small per-agent strip.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Payload {
  available: boolean;
  mean_utilization?: number;
  per_agent?: Array<[number, number, number, number]>;
}

export function LogisticsCapacityChart() {
  const [data, setData] = useState<Payload | null>(null);
  useEffect(() => {
    let cancel = false;
    const tick = async () => {
      try {
        const res = await fetch("/logistics/capacity");
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
        no capacity data yet
      </div>
    );
  }
  const util = data.mean_utilization ?? 0;
  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <Stat label="mean util" value={util * 100} digits={1} suffix="%" accent={util > 0.5} />
        <Stat label="fleet size" value={data.per_agent?.length ?? 0} />
      </div>
      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        Per-agent usage (used / cap)
      </div>
      <ul className="text-[10px] grid grid-cols-2 gap-x-3 gap-y-1">
        {(data.per_agent ?? []).slice(0, 12).map(([agent_id, used, cap, ratio]) => (
          <li key={`ag-${agent_id}`}>
            #{agent_id}: {used}/{cap} ({(ratio * 100).toFixed(0)}%)
          </li>
        ))}
      </ul>
    </div>
  );
}
