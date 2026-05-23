/**
 * Multi-echelon supply chain (Tier 3) tile.
 *
 * Displays the bullwhip ratio per tier, inventory totals across the
 * supplier / distributor / city tiers, and a small sankey-ish strip
 * showing how cities fan into distributors and then suppliers.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Payload {
  available: boolean;
  reason?: string;
  tick?: number;
  n_suppliers?: number;
  n_distributors?: number;
  n_cities?: number;
  inventory_by_tier?: Array<[string, number]>;
  mean_inventory_by_tier?: Array<[string, number]>;
  in_flight_count?: number;
  in_flight_quantity?: number;
  demand_variance?: number;
  bullwhip_per_tier?: Array<[string, number | null]>;
  variance_per_tier?: Array<[string, number]>;
  edges?: Array<[number, number, number]>;
  role_for_node?: Array<[number, string]>;
}

const TIER_ORDER = ["supplier", "distributor", "city"] as const;

function tierLabel(role: string): string {
  if (role === "supplier") return "supplier";
  if (role === "distributor") return "distributor";
  return "city";
}

function formatBullwhip(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  return value.toFixed(2);
}

export function LogisticsEchelonChart() {
  const [data, setData] = useState<Payload | null>(null);
  useEffect(() => {
    let cancel = false;
    const tick = async () => {
      try {
        const res = await fetch("/logistics/echelon");
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
        echelon network not yet initialised — give the simulation a few seconds to warm up
      </div>
    );
  }

  const bullwhip = new Map<string, number | null>(
    (data.bullwhip_per_tier ?? []).map(([role, ratio]) => [role, ratio]),
  );
  const inventory = new Map<string, number>(
    (data.inventory_by_tier ?? []).map(([role, qty]) => [role, qty]),
  );
  const meanInventory = new Map<string, number>(
    (data.mean_inventory_by_tier ?? []).map(([role, qty]) => [role, qty]),
  );
  const variance = new Map<string, number>(
    (data.variance_per_tier ?? []).map(([role, v]) => [role, v]),
  );
  const roleCounts: Record<string, number> = {
    supplier: data.n_suppliers ?? 0,
    distributor: data.n_distributors ?? 0,
    city: data.n_cities ?? 0,
  };

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="tick" value={data.tick ?? 0} />
        <Stat label="demand var" value={data.demand_variance ?? 0} digits={3} />
        <Stat label="in-flight" value={data.in_flight_count ?? 0} />
        <Stat label="in-flight qty" value={data.in_flight_quantity ?? 0} />
      </div>

      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        bullwhip ratio per tier (variance / demand variance)
      </div>
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        {TIER_ORDER.map((role) => {
          const ratio = bullwhip.get(role);
          const isAmplified = ratio != null && Number.isFinite(ratio) && ratio > 1.0;
          return (
            <Stat
              key={`bw-${role}`}
              label={tierLabel(role)}
              value={formatBullwhip(ratio)}
              ember={isAmplified}
              caption={`var ${(variance.get(role) ?? 0).toFixed(2)}`}
            />
          );
        })}
      </div>

      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        inventory by tier
      </div>
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        {TIER_ORDER.map((role) => (
          <Stat
            key={`inv-${role}`}
            label={tierLabel(role)}
            value={inventory.get(role) ?? 0}
            caption={`mean ${(meanInventory.get(role) ?? 0).toFixed(1)} · n=${roleCounts[role]}`}
            accent={role === "supplier"}
          />
        ))}
      </div>

      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        flow (suppliers → distributors → cities)
      </div>
      <div className="text-[10px] leading-snug">
        <div className="flex items-center gap-1 text-[color:var(--color-penumbra-cyan)]">
          <span>{roleCounts.supplier} supplier(s)</span>
          <span className="text-[color:var(--color-penumbra-dim)]">→</span>
          <span>{roleCounts.distributor} distributor(s)</span>
          <span className="text-[color:var(--color-penumbra-dim)]">→</span>
          <span>{roleCounts.city} city(ies)</span>
        </div>
        <div className="text-[color:var(--color-penumbra-muted)] mt-1">
          {(data.edges ?? []).length} edges in the supply-chain DAG
        </div>
      </div>
    </div>
  );
}
