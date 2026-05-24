/**
 * Phase 5 Tier 2 — 1-NN agent fingerprinting.
 *
 * Stable per-agent action histogram + latency stats + trajectory
 * curvature + trade pattern re-identifies agents across matches.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  n_agents?: number;
  n_window_matches?: number;
  reidentification_accuracy?: number;
  random_baseline?: number;
  success?: boolean;
  defence_hint?: string;
}

export function AttackAgentFingerprintChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch("/attacks/agent_fingerprint/demo");
      if (res.ok) setData((await res.json()) as Payload);
    } catch {}
    setBusy(false);
  };

  useEffect(() => {
    void run();
  }, []);

  if (!data?.available) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {busy ? "fingerprinting…" : "attack unavailable"}
      </div>
    );
  }

  const acc = data.reidentification_accuracy ?? 0;
  const base = data.random_baseline ?? 0;
  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "—"} accent />
        <Stat label="n agents" value={data.n_agents ?? 0} digits={0} />
        <Stat label="window matches" value={data.n_window_matches ?? 0} digits={0} />
      </div>
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="re-id accuracy" value={acc} digits={3} ember={data.success ?? false} />
        <Stat label="random baseline" value={base} digits={3} />
        <Stat
          label="advantage ×"
          value={base > 0 ? acc / base : 0}
          digits={2}
          ember={data.success ?? false}
        />
      </div>
      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Defence: {data.defence_hint}
      </div>
      <button
        type="button"
        onClick={run}
        disabled={busy}
        className="border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-ember)] disabled:opacity-50"
      >
        {busy ? "running…" : "re-attempt"}
      </button>
    </div>
  );
}
