/**
 * Phase 5 Tier 3 — k-anonymity privacy-utility curve.
 *
 * Sweep k vs (suppression_rate, adversary_max_reidentification = 1/k).
 * The curve shows the classic Sweeney tradeoff: higher k means lower
 * adversary advantage but more records suppressed.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Point {
  k: number;
  suppression_rate: number;
  adversary_max_reidentification: number;
  n_released: number;
  n_buckets: number;
}

interface Payload {
  available: boolean;
  algorithm?: string;
  quasi_identifiers?: string[];
  n_input?: number;
  curve?: Point[];
}

export function DefenseKAnonymityChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch("/defenses/k_anonymity/demo");
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
        {busy ? "computing…" : "k-anonymity unavailable"}
      </div>
    );
  }

  const points = data.curve;
  const width = 560;
  const height = 170;
  const padLeft = 50;
  const padRight = 10;
  const padTop = 14;
  const padBottom = 26;
  const xMax = Math.max(...points.map((p) => p.k));
  const sx = (k: number) => padLeft + (k / xMax) * (width - padLeft - padRight);
  const sy = (v: number) => padTop + (1 - v) * (height - padTop - padBottom);

  const pathSupp = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.k)},${sy(p.suppression_rate)}`)
    .join(" ");
  const pathAdv = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.k)},${sy(p.adversary_max_reidentification)}`)
    .join(" ");

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "k-anonymity"} accent />
        <Stat label="n input" value={data.n_input ?? 0} digits={0} />
        <Stat
          label="quasi-ids"
          value={(data.quasi_identifiers ?? []).join(" + ")}
          caption="bucket key"
        />
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        role="img"
        aria-label="k vs suppression and adversary advantage"
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
        <path d={pathAdv} stroke="var(--color-penumbra-cyan)" strokeWidth={1.5} fill="none" />
        {points.map((p) => (
          <g key={p.k}>
            <circle
              cx={sx(p.k)}
              cy={sy(p.suppression_rate)}
              r={2.5}
              fill="var(--color-penumbra-ember)"
            />
            <circle
              cx={sx(p.k)}
              cy={sy(p.adversary_max_reidentification)}
              r={2.5}
              fill="var(--color-penumbra-cyan)"
            />
            <text
              x={sx(p.k)}
              y={height - padBottom + 12}
              textAnchor="middle"
              fontSize={8}
              fill="var(--color-penumbra-dim)"
            >
              k={p.k}
            </text>
          </g>
        ))}
        <text x={6} y={padTop + 6} fontSize={8} fill="var(--color-penumbra-cyan)">
          adversary max re-id = 1/k
        </text>
        <text x={6} y={padTop + 18} fontSize={8} fill="var(--color-penumbra-ember)">
          suppression rate (records dropped)
        </text>
      </svg>

      <div className="grid grid-cols-7 gap-1 text-[9px]">
        {points.map((p) => (
          <Stat
            key={p.k}
            label={`k=${p.k}`}
            value={p.suppression_rate}
            digits={3}
            caption={`adv ${p.adversary_max_reidentification.toFixed(2)}`}
          />
        ))}
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Pure suppression — small buckets are dropped, not generalised. ℓ-diversity (sister tile)
        adds a distinctness constraint on the sensitive column to defeat the homogeneity attack.
      </div>
    </div>
  );
}
