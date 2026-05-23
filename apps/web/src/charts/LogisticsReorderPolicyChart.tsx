/**
 * (s, S) reorder policy tile.
 *
 * Renders the configured s / S thresholds and lets the user retune
 * them via fractions of each city's max_inventory.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Pair {
  city: number;
  product: number;
  s: number;
  S: number;
}

interface Payload {
  available: boolean;
  n_pairs_total?: number;
  sample?: Pair[];
  lead_time_ticks?: number;
}

export function LogisticsReorderPolicyChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [s, setS] = useState(0.3);
  const [S, setSS] = useState(0.8);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const res = await fetch("/logistics/reorder-policy");
      if (res.ok) setData((await res.json()) as Payload);
    } catch {}
  };

  useEffect(() => {
    void load();
  }, []);

  const apply = async () => {
    setBusy(true);
    try {
      await fetch(`/logistics/reorder-policy?s_fraction=${s}&S_fraction=${S}`, {
        method: "POST",
      });
      await load();
    } catch {}
    setBusy(false);
  };

  if (!data?.available) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        no reorder policy
      </div>
    );
  }
  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="(s, S) pairs" value={data.n_pairs_total ?? 0} />
        <Stat label="lead time" value={data.lead_time_ticks ?? 0} suffix="t" />
        <Stat label="policy" value="(s, S)" accent />
      </div>
      <div className="grid grid-cols-3 gap-2 text-[10px] items-end">
        <label className="flex flex-col">
          <span className="text-[8px] uppercase text-[color:var(--color-penumbra-dim)]">
            s fraction
          </span>
          <input
            type="number"
            step="0.05"
            min={0.05}
            max={0.95}
            value={s}
            onChange={(e) => setS(Number(e.target.value))}
            className="bg-[color:var(--color-penumbra-bg)] border border-[color:var(--color-penumbra-border)] px-1 py-1 text-[10px]"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-[8px] uppercase text-[color:var(--color-penumbra-dim)]">
            S fraction
          </span>
          <input
            type="number"
            step="0.05"
            min={0.1}
            max={1.0}
            value={S}
            onChange={(e) => setSS(Number(e.target.value))}
            className="bg-[color:var(--color-penumbra-bg)] border border-[color:var(--color-penumbra-border)] px-1 py-1 text-[10px]"
          />
        </label>
        <button
          type="button"
          onClick={apply}
          disabled={busy || !(0 < s && s < S && S <= 1)}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "applying…" : "apply"}
        </button>
      </div>
      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        Sample of policy entries
      </div>
      <ul className="text-[10px] grid grid-cols-2 gap-x-3 gap-y-1">
        {(data.sample ?? []).slice(0, 10).map((p) => (
          <li key={`p-${p.city}-${p.product}`}>
            city {p.city} · prod {p.product}: s={p.s} S={p.S}
          </li>
        ))}
      </ul>
    </div>
  );
}
