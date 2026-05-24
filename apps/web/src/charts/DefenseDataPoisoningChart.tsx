/**
 * Phase 5 Tier 3 — defensive data-poisoning privacy-utility curve.
 *
 * Sweeps the decoy injection rate and shows: attacker max accuracy
 * (the upper bound on a naive re-identification model that trusts
 * every released record), and the utility cost paid by a downstream
 * consumer that ignores the is_decoy flag (shift of mean + std).
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Point {
  rate: number;
  attacker_max_accuracy: number;
  utility_mean_shift: number;
  utility_std_shift: number;
  n_decoy: number;
}

interface Payload {
  available: boolean;
  algorithm?: string;
  n_real?: number;
  curve?: Point[];
}

export function DefenseDataPoisoningChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch("/defenses/data_poisoning/demo");
      if (res.ok) setData((await res.json()) as Payload);
    } catch {}
    setBusy(false);
  };

  useEffect(() => {
    void run();
  }, []);

  if (!data?.available || !data.curve) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {busy ? "computing…" : "decoy injection unavailable"}
      </div>
    );
  }

  const points = data.curve;
  const width = 560;
  const height = 160;
  const padLeft = 50;
  const padRight = 10;
  const padTop = 14;
  const padBottom = 26;
  const xMax = Math.max(...points.map((p) => p.rate));
  const utilMax = Math.max(...points.map((p) => p.utility_mean_shift)) || 1;
  const sx = (r: number) => padLeft + (r / (xMax || 1)) * (width - padLeft - padRight);
  const sy = (v: number) => padTop + (1 - v) * (height - padTop - padBottom);
  const syUtil = (v: number) => padTop + (1 - v / (utilMax || 1)) * (height - padTop - padBottom);

  const pathAcc = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.rate)},${sy(p.attacker_max_accuracy)}`)
    .join(" ");
  const pathUtil = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.rate)},${syUtil(p.utility_mean_shift)}`)
    .join(" ");

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "decoy injection"} accent />
        <Stat label="n real" value={data.n_real ?? 0} digits={0} />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "…" : "resample"}
        </button>
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        role="img"
        aria-label="poisoning rate vs attacker accuracy"
      >
        <line
          x1={padLeft}
          y1={padTop}
          x2={padLeft}
          y2={height - padBottom}
          stroke="var(--color-penumbra-dim)"
        />
        <line
          x1={padLeft}
          y1={height - padBottom}
          x2={width - padRight}
          y2={height - padBottom}
          stroke="var(--color-penumbra-dim)"
        />
        <path d={pathAcc} stroke="var(--color-penumbra-cyan)" strokeWidth={1.5} fill="none" />
        <path
          d={pathUtil}
          stroke="var(--color-penumbra-ember)"
          strokeWidth={1.2}
          fill="none"
          strokeDasharray="3 2"
        />
        {points.map((p) => (
          <g key={p.rate}>
            <circle
              cx={sx(p.rate)}
              cy={sy(p.attacker_max_accuracy)}
              r={2.5}
              fill="var(--color-penumbra-cyan)"
            />
            <circle
              cx={sx(p.rate)}
              cy={syUtil(p.utility_mean_shift)}
              r={2.5}
              fill="var(--color-penumbra-ember)"
            />
            <text
              x={sx(p.rate)}
              y={height - padBottom + 12}
              textAnchor="middle"
              fontSize={8}
              fill="var(--color-penumbra-dim)"
            >
              {p.rate.toFixed(2)}
            </text>
          </g>
        ))}
        <text x={6} y={padTop + 6} fontSize={8} fill="var(--color-penumbra-cyan)">
          attacker max acc (left, 0..1)
        </text>
        <text x={6} y={padTop + 18} fontSize={8} fill="var(--color-penumbra-ember)">
          util mean shift (right, scaled)
        </text>
      </svg>

      <div className="grid grid-cols-5 gap-1 text-[9px]">
        {points.slice(0, 5).map((p) => (
          <Stat
            key={p.rate}
            label={`r=${p.rate.toFixed(2)}`}
            value={p.attacker_max_accuracy}
            digits={3}
            caption={`util Δμ ${p.utility_mean_shift.toFixed(2)}`}
          />
        ))}
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Decoys are sampled per-field from the empirical distribution of the real records and flagged
        with `is_decoy=True` so defender-side consumers can filter them. The attacker is assumed to
        ignore the flag — its accuracy on the contaminated stream is bounded by 1 − rate.
      </div>
    </div>
  );
}
