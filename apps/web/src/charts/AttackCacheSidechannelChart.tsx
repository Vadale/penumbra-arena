/**
 * Phase 5 Tier 2 — Flush+Reload cache side-channel against CKKS.
 *
 * Time sparse vs dense ciphertext add; Welch t-test the distributions.
 * TenSEAL/OpenFHE pad to the full polynomial degree on every op, so
 * `leak_detected` MUST come back False — that's the educational point.
 */

import { useEffect, useState } from "react";
import { FetchError, Stat } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  n_samples?: number;
  vector_size?: number;
  welch_t?: number;
  p_value?: number;
  leak_detected?: boolean;
  sparse_median_us?: number;
  dense_median_us?: number;
  success?: boolean;
  expectation?: string;
  defence_hint?: string;
  reason?: string;
}

export function AttackCacheSidechannelChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/attacks/cache_sidechannel/demo");
      if (!res.ok) {
        setError(`HTTP ${res.status} on /attacks/cache_sidechannel/demo`);
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
        {busy ? "timing CKKS add…" : (data?.reason ?? "attack unavailable")}
      </div>
    );
  }

  const leaked = data.leak_detected ?? false;
  return (
    <div className="font-mono space-y-3">
      {error && <FetchError message={error} />}
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "—"} accent />
        <Stat label="n samples" value={data.n_samples ?? 0} digits={0} />
        <Stat label="vector size" value={data.vector_size ?? 0} digits={0} />
      </div>
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="welch t" value={data.welch_t ?? 0} digits={2} ember={leaked} />
        <Stat label="p value" value={data.p_value ?? 0} digits={3} />
        <Stat
          label="leak detected?"
          value={leaked ? "yes" : "no"}
          accent={!leaked}
          ember={leaked}
        />
      </div>
      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <Stat label="sparse median μs" value={data.sparse_median_us ?? 0} digits={2} />
        <Stat label="dense median μs" value={data.dense_median_us ?? 0} digits={2} />
      </div>
      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Expectation: {data.expectation}. Defence: {data.defence_hint}
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
