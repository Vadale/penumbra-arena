/**
 * Phase 5 Tier 2 — Shokri shadow-model membership inference.
 *
 * Train N small shadow models; their per-sample confidence vectors
 * teach a meta-classifier that distinguishes "this was in training"
 * from "this was not" on the real target policy.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  n_shadows?: number;
  membership_accuracy?: number;
  advantage_over_chance?: number;
  success?: boolean;
  defence_hint?: string;
}

export function AttackMembershipInferenceChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch("/attacks/membership_inference/demo");
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
        {busy ? "training shadows…" : "attack unavailable"}
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "—"} accent />
        <Stat label="shadow models" value={data.n_shadows ?? 0} digits={0} />
        <Stat
          label="member acc"
          value={data.membership_accuracy ?? 0}
          digits={3}
          ember={data.success ?? false}
        />
      </div>
      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <Stat
          label="advantage over chance"
          value={data.advantage_over_chance ?? 0}
          digits={3}
          ember={data.success ?? false}
        />
        <Stat label="success?" value={data.success ? "yes" : "no"} ember={data.success ?? false} />
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
