/**
 * Wesolowski VDF demo with compute-to-verify asymmetry.
 *
 * VDFs are useful because they encode wall-clock time. Computing one
 * is INHERENTLY SEQUENTIAL (no parallel speedup); verifying is fast.
 * The ratio is what makes them useful for unbiasable randomness.
 */

import { useEffect, useState } from "react";
import { FetchError } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  delay?: number;
  x_short?: string;
  y_short?: string;
  proof_short?: string;
  compute_ms?: number;
  verify_ms?: number;
  compute_to_verify_ratio?: number;
  honest_verifies?: boolean;
  tampered_verifies?: boolean;
}

export function VDFChart() {
  const [delay, setDelay] = useState(50000);
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/crypto/vdf/demo?delay=${delay}`);
      if (!res.ok) {
        setError(`HTTP ${res.status} on /crypto/vdf/demo`);
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
    // biome-ignore lint/correctness/useExhaustiveDependencies: one-shot on mount
  }, []);

  return (
    <div className="font-mono space-y-3">
      {error && <FetchError message={error} />}
      <div className="flex items-center gap-2 text-[10px]">
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          delay (squarings)
        </label>
        <input
          type="number"
          min={1000}
          max={1000000}
          step={1000}
          value={delay}
          onChange={(e) => setDelay(Number(e.target.value))}
          className="w-24 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "computing…" : "evaluate + verify"}
        </button>
      </div>

      {data?.available ? (
        <>
          <div className="grid grid-cols-4 gap-2 text-[10px]">
            <Stat label="algorithm" value={data.algorithm ?? "—"} accent />
            <Stat label="delay" value={String(data.delay ?? 0)} />
            <Stat label="compute" value={`${(data.compute_ms ?? 0).toFixed(1)} ms`} accent />
            <Stat label="verify" value={`${(data.verify_ms ?? 0).toFixed(2)} ms`} accent />
          </div>
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <Stat
              label="compute/verify ratio"
              value={`${(data.compute_to_verify_ratio ?? 0).toFixed(0)}×`}
              accent
              caption="higher = better asymmetry"
            />
            <Stat
              label="result"
              value={
                data.honest_verifies && !data.tampered_verifies ? "OK + tamper REJECTED" : "FAIL"
              }
              accent={data.honest_verifies && !data.tampered_verifies}
              ember={!data.honest_verifies || data.tampered_verifies}
            />
          </div>

          <Block label="x (input)" value={data.x_short ?? ""} />
          <Block label="y = x^(2^T) mod p" value={data.y_short ?? ""} accent />
          <Block label="π (Wesolowski proof)" value={data.proof_short ?? ""} />

          <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
            verify: π^prime · x^r ≡ y (mod p), with prime = hash-to-prime(x, y, T), r = 2^T mod
            prime. Cheap because we only need ONE modular exponentiation instead of T sequential
            squarings.
          </div>
        </>
      ) : (
        <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
          {busy ? "computing VDF…" : "click evaluate + verify"}
        </div>
      )}
    </div>
  );
}

function Block({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div
        className={`border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-2 text-[11px] break-all ${accent ? "text-[color:var(--color-penumbra-cyan)]" : "text-[color:var(--color-penumbra-text)]"}`}
      >
        0x{value}…
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
  ember,
  caption,
}: {
  label: string;
  value: string;
  accent?: boolean;
  ember?: boolean;
  caption?: string;
}) {
  const cls = ember
    ? "text-[color:var(--color-penumbra-ember)]"
    : accent
      ? "text-[color:var(--color-penumbra-cyan)]"
      : "text-[color:var(--color-penumbra-text)]";
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div className={`tabular-nums ${cls}`}>{value}</div>
      {caption && (
        <div className="text-[8px] text-[color:var(--color-penumbra-dim)]">{caption}</div>
      )}
    </div>
  );
}
