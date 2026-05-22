/**
 * Slashing — submit forged-equivocation evidence to the chain.
 *
 * Uses the SAFE demo endpoint `/chain/_demo/self-slash` which signs
 * conflicting blocks on the server side, files the evidence, and
 * returns the resulting slashing tx. We display the resulting state.
 */

import { useEffect, useState } from "react";

interface SlashResponse {
  validator_index: number;
  offender_short: string;
  height: number;
  slashed: number;
  active_after: number;
}

export function SlashingChart() {
  const [active, setActive] = useState<{ index: number; bls_short: string; slashed: boolean }[]>(
    [],
  );
  const [lastResult, setLastResult] = useState<SlashResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [pickedIndex, setPickedIndex] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const grab = async () => {
      try {
        const res = await fetch("/chain/vrf-leader");
        if (!res.ok) return;
        const payload = (await res.json()) as {
          validators?: { index: number; bls_short: string; slashed: boolean }[];
        };
        if (!cancelled) setActive(payload.validators ?? []);
      } catch {}
    };
    void grab();
    const t = window.setInterval(grab, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  const submit = async () => {
    if (pickedIndex === null) return;
    setBusy(true);
    try {
      const res = await fetch(`/chain/_demo/self-slash?validator_index=${pickedIndex}`, {
        method: "POST",
      });
      if (res.ok) {
        setLastResult((await res.json()) as SlashResponse);
      }
    } catch {}
    setBusy(false);
  };

  const candidates = active.filter((v) => !v.slashed);

  return (
    <div className="font-mono space-y-3">
      <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
        Submit equivocation evidence against a validator. The demo endpoint
        signs two CONFLICTING block hashes with the chosen validator's secret,
        files them as a SlashingEvidence, and the chain folds the result into
        the next block (validator pubkey banned + active_indices updated).
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          pick an active validator
        </div>
        <div className="flex flex-wrap gap-1">
          {candidates.map((v) => (
            <button
              key={v.index}
              type="button"
              onClick={() => setPickedIndex(v.index)}
              className={
                v.index === pickedIndex
                  ? "border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-2 py-0.5 text-[10px] text-[color:var(--color-penumbra-ember)]"
                  : "border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-0.5 text-[10px] text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-text)]"
              }
            >
              v{v.index} · {v.bls_short}…
            </button>
          ))}
          {candidates.length === 0 && (
            <span className="text-[10px] text-[color:var(--color-penumbra-dim)]">
              all validators already slashed
            </span>
          )}
        </div>
      </div>

      <button
        type="button"
        onClick={submit}
        disabled={busy || pickedIndex === null}
        className="border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-3 py-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)] disabled:opacity-50"
      >
        {busy ? "submitting…" : "submit equivocation evidence"}
      </button>

      {lastResult && (
        <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-2 text-[10px]">
          <div className="text-[color:var(--color-penumbra-ember)]">
            slashed v{lastResult.validator_index} ({lastResult.offender_short}…)
          </div>
          <div className="text-[color:var(--color-penumbra-muted)]">
            evidence height = {lastResult.height} · total slashed ={" "}
            {lastResult.slashed} · active validators remaining ={" "}
            {lastResult.active_after}
          </div>
        </div>
      )}
    </div>
  );
}
