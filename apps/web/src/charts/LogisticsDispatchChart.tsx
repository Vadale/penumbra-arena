/**
 * Carrier-dispatch tile.
 *
 * Greedy nearest-agent assignment + per-agent earnings. The dispatcher
 * binds each order to one carrier; fulfilment fires when that carrier
 * reaches the order's destination city with the requested product in
 * cargo. Phantom carrier (id = -1) is a safety fallback so orders
 * never deadlock if every agent is idle.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Payload {
  available: boolean;
  n_pending?: number;
  n_assigned?: number;
  n_unassigned?: number;
  n_fulfilled?: number;
  n_placed?: number;
  n_phantom_fulfilled?: number;
  mean_carrier_revenue?: number;
  fulfilment_efficiency?: number;
  top_carriers?: Array<[number, number]>;
}

export function LogisticsDispatchChart() {
  const [data, setData] = useState<Payload | null>(null);
  useEffect(() => {
    let cancel = false;
    const tick = async () => {
      try {
        const res = await fetch("/logistics/dispatch");
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
        no dispatch data yet
      </div>
    );
  }
  const efficiency = data.fulfilment_efficiency ?? 0;
  const top = data.top_carriers ?? [];
  const maxReward = top.length > 0 ? Math.max(...top.map(([, r]) => r), 1) : 1;
  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="pending" value={data.n_pending ?? 0} />
        <Stat label="assigned" value={data.n_assigned ?? 0} accent />
        <Stat label="unassigned" value={data.n_unassigned ?? 0} />
        <Stat label="fulfilled" value={data.n_fulfilled ?? 0} />
        <Stat label="placed" value={data.n_placed ?? 0} />
        <Stat
          label="phantom"
          value={data.n_phantom_fulfilled ?? 0}
          ember={(data.n_phantom_fulfilled ?? 0) > 0}
        />
        <Stat
          label="efficiency"
          value={efficiency * 100}
          digits={1}
          suffix="%"
          accent={efficiency > 0.5}
        />
        <Stat label="mean revenue" value={data.mean_carrier_revenue ?? 0} digits={2} suffix="c" />
      </div>
      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        Top 10 carriers (reward earned)
      </div>
      {top.length === 0 ? (
        <div className="text-[10px] text-[color:var(--color-penumbra-muted)]">
          no carriers paid yet
        </div>
      ) : (
        <ul className="space-y-1">
          {top.map(([agent_id, reward]) => {
            const ratio = reward / maxReward;
            return (
              <li
                key={`car-${agent_id}`}
                className="grid grid-cols-[3rem_1fr_3rem] gap-2 text-[10px]"
              >
                <span>#{agent_id}</span>
                <span className="relative block h-3 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)]">
                  <span
                    className="absolute inset-y-0 left-0 bg-[color:var(--color-penumbra-cyan)]"
                    style={{ width: `${Math.max(0, Math.min(1, ratio)) * 100}%` }}
                  />
                </span>
                <span className="text-right tabular-nums">{reward.toFixed(1)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
