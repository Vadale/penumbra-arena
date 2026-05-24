/**
 * Phase 5 Tier 2 — HMM trajectory fingerprinting.
 *
 * Per-agent Baum-Welch HMM + forward log-likelihood classification.
 * Captures temporal structure that 1-NN over static features misses.
 */

import { useEffect, useState } from "react";
import { FetchError, Stat } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  n_agents?: number;
  n_train_matches?: number;
  classification_accuracy?: number;
  random_baseline?: number;
  success?: boolean;
  defence_hint?: string;
}

export function AttackTrajectoryFingerprintChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/attacks/trajectory_fingerprint/demo");
      if (!res.ok) {
        setError(`HTTP ${res.status} on /attacks/trajectory_fingerprint/demo`);
      } else {
        setData((await res.json()) as Payload);
      }
    } catch (exc) {
      setError(`network error: ${exc instanceof Error ? exc.message : String(exc)}`);
    }
    setBusy(false);
  };

  useEffect(() => {
    void run();
  }, []);

  if (!data?.available) {
    if (error) return <FetchError message={error} />;
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {busy ? "fitting HMMs…" : "attack unavailable"}
      </div>
    );
  }

  const acc = data.classification_accuracy ?? 0;
  const base = data.random_baseline ?? 0;
  return (
    <div className="font-mono space-y-3">
      {error && <FetchError message={error} />}
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "—"} accent />
        <Stat label="n agents" value={data.n_agents ?? 0} digits={0} />
        <Stat label="train matches" value={data.n_train_matches ?? 0} digits={0} />
      </div>
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="classify acc" value={acc} digits={3} ember={data.success ?? false} />
        <Stat label="baseline" value={base} digits={3} />
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
