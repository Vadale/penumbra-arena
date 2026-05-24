/**
 * Phase 5 Tier 3 — request obfuscation (Bonferroni + dummy queries).
 *
 * Sweeps dummy count vs (per-query corrected ε, attacker budget
 * inflation). Bonferroni divides the family-wise ε by the family
 * size; injecting dummies grows the family the attacker has to budget
 * for, draining its DP budget proportionally faster.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Point {
  n_dummies: number;
  family_size: number;
  per_query_epsilon_corrected: number;
  attacker_budget_inflation: number;
  dummy_query_rate: number;
}

interface Payload {
  available: boolean;
  algorithm?: string;
  n_real_queries?: number;
  family_wise_epsilon?: number;
  curve?: Point[];
}

export function DefenseRequestObfuscationChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch("/defenses/request_obfuscation/demo");
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
        {busy ? "computing…" : "obfuscation unavailable"}
      </div>
    );
  }

  const points = data.curve;
  const width = 560;
  const height = 160;
  const padLeft = 60;
  const padRight = 10;
  const padTop = 14;
  const padBottom = 26;
  const xMax = Math.max(...points.map((p) => p.n_dummies), 1);
  const inflMax = Math.max(...points.map((p) => p.attacker_budget_inflation), 1);
  const sx = (n: number) => padLeft + (n / xMax) * (width - padLeft - padRight);
  const sy = (v: number, max: number) => padTop + (1 - v / max) * (height - padTop - padBottom);

  const pathInfl = points
    .map(
      (p, i) =>
        `${i === 0 ? "M" : "L"}${sx(p.n_dummies)},${sy(p.attacker_budget_inflation, inflMax)}`,
    )
    .join(" ");

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "obfuscation"} accent />
        <Stat label="n real queries" value={data.n_real_queries ?? 0} digits={0} />
        <Stat label="family-wise ε" value={data.family_wise_epsilon ?? 1} digits={2} />
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        role="img"
        aria-label="dummy count vs attacker budget inflation"
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
        <path d={pathInfl} stroke="var(--color-penumbra-cyan)" strokeWidth={1.5} fill="none" />
        {points.map((p) => (
          <g key={p.n_dummies}>
            <circle
              cx={sx(p.n_dummies)}
              cy={sy(p.attacker_budget_inflation, inflMax)}
              r={2.5}
              fill="var(--color-penumbra-cyan)"
            />
            <text
              x={sx(p.n_dummies)}
              y={height - padBottom + 12}
              textAnchor="middle"
              fontSize={8}
              fill="var(--color-penumbra-dim)"
            >
              +{p.n_dummies}
            </text>
          </g>
        ))}
        <text x={6} y={padTop + 6} fontSize={8} fill="var(--color-penumbra-cyan)">
          attacker budget inflation × (higher better)
        </text>
      </svg>

      <div className="grid grid-cols-6 gap-1 text-[9px]">
        {points.map((p) => (
          <Stat
            key={p.n_dummies}
            label={`+${p.n_dummies}`}
            value={p.attacker_budget_inflation}
            digits={0}
            suffix="×"
            caption={`ε/q ${p.per_query_epsilon_corrected.toExponential(1)}`}
          />
        ))}
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Bonferroni divides the family-wise ε across all queries, so an attacker that wants its usual
        family-wise guarantee must accept a smaller per-query budget. Dummies grow the family size,
        draining the attacker's DP accountant proportionally faster.
      </div>
    </div>
  );
}
