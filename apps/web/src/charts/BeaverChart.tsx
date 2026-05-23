/**
 * Beaver triples — secret multiplication via additive shares.
 *
 * N parties each hold an additive share of x, y, and a Beaver triple
 * (a, b, c=a*b). Local arithmetic + one round of broadcast lets them
 * collectively compute x·y without anyone learning x or y.
 */

import { useEffect, useState } from "react";

interface Payload {
  available: boolean;
  algorithm?: string;
  n_parties?: number;
  x?: number;
  y?: number;
  x_shares?: string[];
  y_shares?: string[];
  z_shares?: string[];
  expected_product?: number;
  reconstructed?: number;
  matches_modulo_p?: boolean;
}

export function BeaverChart() {
  const [nParties, setNParties] = useState(3);
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch(`/crypto/beaver/demo?n_parties=${nParties}`);
      if (res.ok) setData((await res.json()) as Payload);
    } catch {}
    setBusy(false);
  };

  useEffect(() => {
    void run();
  }, [nParties]);

  if (!data?.available) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {busy ? "running SMPC…" : "Beaver unavailable"}
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      <div className="flex items-center gap-2 text-[10px]">
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          parties
        </label>
        <input
          type="number"
          min={2}
          max={8}
          value={nParties}
          onChange={(e) => setNParties(Math.max(2, Math.min(8, Number(e.target.value))))}
          className="w-14 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "computing…" : "re-run"}
        </button>
      </div>

      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="x" value={String(data.x ?? 0)} accent />
        <Stat label="y" value={String(data.y ?? 0)} accent />
        <Stat label="expected x·y" value={String(data.expected_product ?? 0)} />
        <Stat label="reconstructed" value={String(data.reconstructed ?? 0)} accent />
      </div>

      <ShareGrid label="x shares (additive)" shares={data.x_shares ?? []} />
      <ShareGrid label="y shares (additive)" shares={data.y_shares ?? []} />
      <ShareGrid label="z shares (output)" shares={data.z_shares ?? []} accent />

      <Verdict label={`Σ z_i ≡ x · y (mod p)`} ok={data.matches_modulo_p ?? false} />

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Beaver protocol: dealer shares (a, b, c=a·b). Each party computes d_i = x_i − a_i, e_i = y_i
        − b_i; opens Σd and Σe. Local output: z_i = c_i + d·b_i + e·a_i + (i==0 ? d·e : 0). Σ z_i =
        x·y mod p without anyone seeing x or y.
      </div>
    </div>
  );
}

function ShareGrid({
  label,
  shares,
  accent,
}: {
  label: string;
  shares: string[];
  accent?: boolean;
}) {
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div className="flex flex-wrap gap-1 text-[10px]">
        {shares.map((s, i) => (
          <span
            key={`${label}-${i}-${s}`}
            className={`border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1.5 py-0.5 tabular-nums ${accent ? "text-[color:var(--color-penumbra-cyan)]" : "text-[color:var(--color-penumbra-muted)]"}`}
          >
            P{i}: 0x{s}
          </span>
        ))}
      </div>
    </div>
  );
}

function Verdict({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div
      className={
        ok
          ? "border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] p-2"
          : "border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] p-2"
      }
    >
      <div
        className={
          ok
            ? "text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]"
            : "text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)]"
        }
      >
        {label}: {ok ? "MATCH" : "NO MATCH"}
      </div>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
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
