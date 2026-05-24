/**
 * Phase 5 Tier 2 — reward poisoning on a 4-armed bandit.
 *
 * Inject inflated rewards on 5% of training episodes, all routed to
 * the attacker's `target_action`. The poisoned policy drifts toward
 * the attacker's preference, away from the true best action.
 */

import { useEffect, useState } from "react";
import { FetchError, Stat } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  n_episodes?: number;
  perturbation_rate?: number;
  true_best_action?: number;
  target_action?: number;
  clean_top_action?: number;
  poisoned_top_action?: number;
  kl_divergence?: number;
  drop_pct_on_true_best?: number;
  success?: boolean;
  defence_hint?: string;
}

export function AttackRewardPoisoningChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/attacks/reward_poisoning/demo");
      if (!res.ok) {
        setError(`HTTP ${res.status} on /attacks/reward_poisoning/demo`);
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
        {busy ? "training poisoned policy…" : "attack unavailable"}
      </div>
    );
  }

  const drift = data.poisoned_top_action !== data.clean_top_action;
  return (
    <div className="font-mono space-y-3">
      {error && <FetchError message={error} />}
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "—"} accent />
        <Stat label="episodes" value={data.n_episodes ?? 0} digits={0} />
        <Stat label="poison rate" value={data.perturbation_rate ?? 0} digits={3} suffix=" frac" />
      </div>
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="true best" value={data.true_best_action ?? -1} digits={0} accent />
        <Stat label="target" value={data.target_action ?? -1} digits={0} ember />
        <Stat label="clean top" value={data.clean_top_action ?? -1} digits={0} />
        <Stat
          label="poisoned top"
          value={data.poisoned_top_action ?? -1}
          digits={0}
          ember={drift}
        />
      </div>
      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <Stat label="KL(poisoned ‖ clean)" value={data.kl_divergence ?? 0} digits={3} />
        <Stat
          label="drop pct on true best"
          value={data.drop_pct_on_true_best ?? 0}
          digits={3}
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
