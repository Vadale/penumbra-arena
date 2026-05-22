/**
 * Shamir secret sharing (n, t) demo.
 *
 * Pedagogically: a secret S becomes N shares such that ANY T of them
 * recover S exactly, but FEWER than T recover nothing (information-
 * theoretic guarantee, not "very hard").
 */

import { useEffect, useState } from "react";

interface Share {
  x: number;
  y_short: string;
}
interface Payload {
  available: boolean;
  algorithm?: string;
  secret?: number;
  n_shares?: number;
  threshold?: number;
  shares?: Share[];
  recovered_from_t?: number;
  recovered_matches?: boolean;
  recovered_from_t_minus_1?: number;
  leaks_at_t_minus_1?: boolean;
}

export function ShamirChart() {
  const [n, setN] = useState(5);
  const [t, setT] = useState(3);
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch(`/crypto/shamir/demo?n=${n}&t=${t}`);
      if (res.ok) setData((await res.json()) as Payload);
    } catch {}
    setBusy(false);
  };

  useEffect(() => {
    void run();
    // biome-ignore lint/correctness/useExhaustiveDependencies: re-run when params change
  }, [run]);

  return (
    <div className="font-mono space-y-3">
      <div className="flex items-center gap-3 text-[10px]">
        <label className="flex items-center gap-1">
          <span className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">n</span>
          <input
            type="number"
            min={2}
            max={12}
            value={n}
            onChange={(e) => setN(Math.max(2, Math.min(12, Number(e.target.value))))}
            className="w-14 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
          />
        </label>
        <label className="flex items-center gap-1">
          <span className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">t</span>
          <input
            type="number"
            min={2}
            max={n}
            value={t}
            onChange={(e) => setT(Math.max(2, Math.min(n, Number(e.target.value))))}
            className="w-14 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
          />
        </label>
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "splitting…" : "re-split"}
        </button>
      </div>

      {data?.available && (
        <>
          <div className="grid grid-cols-3 gap-2 text-[10px]">
            <Stat label="secret" value={String(data.secret ?? 0)} accent />
            <Stat label="n / t" value={`${data.n_shares} / ${data.threshold}`} accent />
            <Stat label="field" value="GF(2^61 - 1)" />
          </div>

          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
              shares (x, y) — each one alone reveals NOTHING about the secret
            </div>
            <div className="space-y-1">
              {(data.shares ?? []).map((s) => (
                <div
                  key={`share-${s.x}`}
                  className="flex items-center justify-between border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 text-[10px]"
                >
                  <span className="text-[color:var(--color-penumbra-muted)]">x = {s.x}</span>
                  <span className="tabular-nums text-[color:var(--color-penumbra-text)]">
                    y = 0x{s.y_short}…
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Verdict
              label={`${data.threshold} shares → recover`}
              ok={data.recovered_matches ?? false}
              caption={`recovered = ${data.recovered_from_t}`}
            />
            <Verdict
              label={`${(data.threshold ?? 2) - 1} shares → noise`}
              ok={data.leaks_at_t_minus_1 ?? false}
              inverted
              caption={`recovered = ${data.recovered_from_t_minus_1} (garbage)`}
            />
          </div>

          <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
            Each share is a point on a degree-(t-1) polynomial. t points uniquely determine the
            polynomial (and hence the secret = f(0)). t-1 points fit infinitely many polynomials —
            every value of f(0) is equally likely.
          </div>
        </>
      )}
    </div>
  );
}

function Verdict({
  label,
  ok,
  caption,
  inverted,
}: {
  label: string;
  ok: boolean;
  caption: string;
  inverted?: boolean;
}) {
  const passing = inverted ? !ok : ok;
  return (
    <div
      className={
        passing
          ? "border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] p-2"
          : "border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] p-2"
      }
    >
      <div
        className={
          passing
            ? "text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]"
            : "text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)]"
        }
      >
        {label}: {ok ? "MATCH" : "NO MATCH"}
      </div>
      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">{caption}</div>
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
