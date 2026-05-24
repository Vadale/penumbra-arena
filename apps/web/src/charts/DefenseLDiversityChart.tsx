/**
 * Phase 5 Tier 3 — ℓ-diversity privacy-utility curve at fixed k.
 *
 * Sweep ℓ vs (suppression_rate, min distinct sensitive values per
 * bucket). Larger ℓ → stronger homogeneity-attack defense → more
 * suppression. The dashboard shows the tradeoff at a fixed k.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Point {
  l: number;
  k: number;
  suppression_rate: number;
  min_distinct_sensitive: number;
  homogeneity_safe: number;
  n_released: number;
}

interface Payload {
  available: boolean;
  algorithm?: string;
  quasi_identifiers?: string[];
  sensitive?: string;
  k?: number;
  n_input?: number;
  curve?: Point[];
}

export function DefenseLDiversityChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch("/defenses/l_diversity/demo");
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
        {busy ? "computing…" : "ℓ-diversity unavailable"}
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
  const xMax = Math.max(...points.map((p) => p.l), 1);
  const sx = (l: number) => padLeft + (l / xMax) * (width - padLeft - padRight);
  const sy = (v: number) => padTop + (1 - v) * (height - padTop - padBottom);

  const pathSupp = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.l)},${sy(p.suppression_rate)}`)
    .join(" ");

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "ℓ-diversity"} accent />
        <Stat label="k (floor)" value={data.k ?? 0} digits={0} />
        <Stat label="sensitive col" value={data.sensitive ?? "—"} />
        <Stat label="n input" value={data.n_input ?? 0} digits={0} />
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        role="img"
        aria-label="ℓ vs suppression rate"
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
        <path d={pathSupp} stroke="var(--color-penumbra-ember)" strokeWidth={1.5} fill="none" />
        {points.map((p) => (
          <g key={p.l}>
            <circle
              cx={sx(p.l)}
              cy={sy(p.suppression_rate)}
              r={2.5}
              fill={
                p.homogeneity_safe ? "var(--color-penumbra-cyan)" : "var(--color-penumbra-ember)"
              }
            />
            <text
              x={sx(p.l)}
              y={height - padBottom + 12}
              textAnchor="middle"
              fontSize={8}
              fill="var(--color-penumbra-dim)"
            >
              ℓ={p.l}
            </text>
          </g>
        ))}
        <text x={6} y={padTop + 6} fontSize={8} fill="var(--color-penumbra-ember)">
          suppression rate (records dropped)
        </text>
        <text x={6} y={padTop + 18} fontSize={8} fill="var(--color-penumbra-cyan)">
          cyan dot = homogeneity-safe
        </text>
      </svg>

      <div className="grid grid-cols-4 gap-1 text-[9px]">
        {points.map((p) => (
          <Stat
            key={p.l}
            label={`ℓ=${p.l}`}
            value={p.suppression_rate}
            digits={3}
            caption={`min distinct ${p.min_distinct_sensitive}`}
          />
        ))}
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        ℓ-diversity strengthens k-anonymity by requiring ≥ ℓ distinct sensitive values per bucket.
        Defeats the homogeneity attack (all records in a k-bucket sharing the same sensitive value).
        t-closeness is the next upgrade — defeats the skewness attack.
      </div>
    </div>
  );
}
