/**
 * Phase 5 Tier 2 — Deep-Leakage-from-Gradients model inversion.
 *
 * Reconstruct a secret training observation by minimising the L2
 * distance between the leaked gradient and the gradient produced by
 * the model on a candidate input. Defence: DP-SGD destroys the signal.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  n_features?: number;
  n_classes?: number;
  naive_cosine_similarity?: number;
  naive_l2_error?: number;
  defended_l2_error?: number;
  success?: boolean;
  defence_hint?: string;
}

export function AttackModelInversionChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch("/attacks/model_inversion/demo");
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
        {busy ? "inverting…" : "attack unavailable"}
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "—"} accent />
        <Stat label="features" value={data.n_features ?? 0} digits={0} />
        <Stat label="classes" value={data.n_classes ?? 0} digits={0} />
      </div>
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat
          label="naive cos sim"
          value={data.naive_cosine_similarity ?? 0}
          digits={3}
          ember={data.success ?? false}
        />
        <Stat label="naive L2 err" value={data.naive_l2_error ?? 0} digits={3} />
        <Stat label="defended L2 err" value={data.defended_l2_error ?? 0} digits={3} accent />
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
