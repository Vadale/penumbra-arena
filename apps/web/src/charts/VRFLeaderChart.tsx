/**
 * VRF leader rotation panel.
 *
 * Shows the validator set, who proposed each of the recent N blocks
 * (with the BLS pubkey short prefix + the VRF beta short prefix), and
 * the seed the NEXT election will use. Helps you SEE that leadership
 * rotates fairly across validators.
 */

import { useEffect, useState } from "react";

interface Validator {
  index: number;
  bls_short: string;
  vrf_short: string;
  slashed: boolean;
}
interface RecentBlock {
  height: number;
  leader_index: number;
  leader_short: string;
  vrf_beta_short: string;
  timestamp_ns: number;
}
interface Snapshot {
  validators: Validator[];
  recent: RecentBlock[];
  next_seed: string;
  active: number[];
  current_height: number;
}

export function VRFLeaderChart() {
  const [data, setData] = useState<Snapshot | null>(null);
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await fetch("/chain/vrf-leader");
        if (!res.ok) return;
        const payload = (await res.json()) as Snapshot;
        if (!cancelled) setData(payload);
      } catch {}
    };
    void tick();
    const t = window.setInterval(tick, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  if (!data) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        loading VRF state…
      </div>
    );
  }
  // Count how often each validator has been leader in the recent window.
  const counts = new Map<number, number>();
  for (const b of data.recent) counts.set(b.leader_index, (counts.get(b.leader_index) ?? 0) + 1);
  const maxCount = Math.max(...Array.from(counts.values()), 1);

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="height" value={data.current_height} accent />
        <Stat label="validators" value={data.validators.length} />
        <Stat label="active" value={data.active.length} accent />
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          validator set + leader frequency (recent {data.recent.length} blocks)
        </div>
        <svg viewBox={`0 0 560 ${data.validators.length * 22 + 6}`} width="100%" role="img" aria-label="validators">
          {data.validators.map((v) => {
            const y = v.index * 22 + 4;
            const c = counts.get(v.index) ?? 0;
            const w = (c / maxCount) * 280;
            return (
              <g key={`v-${v.index}`}>
                <text
                  x={6}
                  y={y + 11}
                  fontSize={10}
                  dominantBaseline="central"
                  fill={
                    v.slashed
                      ? "var(--color-penumbra-ember)"
                      : "var(--color-penumbra-muted)"
                  }
                >
                  v{v.index} · bls {v.bls_short}…
                </text>
                <rect
                  x={240}
                  y={y}
                  width={Math.max(2, w)}
                  height={16}
                  fill={
                    v.slashed
                      ? "color-mix(in srgb, var(--color-penumbra-ember) 50%, transparent)"
                      : "color-mix(in srgb, var(--color-penumbra-cyan) 35%, transparent)"
                  }
                  stroke={v.slashed ? "var(--color-penumbra-ember)" : "var(--color-penumbra-cyan)"}
                  strokeWidth={0.7}
                />
                <text
                  x={244 + Math.max(2, w)}
                  y={y + 11}
                  fontSize={10}
                  dominantBaseline="central"
                  fill="var(--color-penumbra-text)"
                >
                  {c}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          recent blocks
        </div>
        <table className="w-full text-[10px]">
          <thead className="text-[color:var(--color-penumbra-dim)]">
            <tr>
              <th className="text-left font-normal">height</th>
              <th className="text-left font-normal">leader</th>
              <th className="text-left font-normal">bls</th>
              <th className="text-left font-normal">vrf β</th>
            </tr>
          </thead>
          <tbody>
            {[...data.recent].reverse().map((b) => (
              <tr key={`b-${b.height}`} className="border-t border-[color:var(--color-penumbra-border)]">
                <td className="py-0.5 text-[color:var(--color-penumbra-cyan)]">#{b.height}</td>
                <td className="py-0.5 text-[color:var(--color-penumbra-text)]">v{b.leader_index}</td>
                <td className="py-0.5 tabular-nums text-[color:var(--color-penumbra-muted)]">{b.leader_short}…</td>
                <td className="py-0.5 tabular-nums text-[color:var(--color-penumbra-dim)]">{b.vrf_beta_short}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
        next election seed = <span className="text-[color:var(--color-penumbra-muted)]">{data.next_seed}…</span>
      </div>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div
        className={`tabular-nums ${accent ? "text-[color:var(--color-penumbra-cyan)]" : "text-[color:var(--color-penumbra-text)]"}`}
      >
        {value}
      </div>
    </div>
  );
}
