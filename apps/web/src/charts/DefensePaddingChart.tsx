/**
 * Phase 5 Tier 3 — request padding privacy-utility curve + cover schedule.
 *
 * Padding to a fixed bucket collapses distinct sizes to 1 (privacy on
 * the size channel); the bandwidth overhead = target_size / mean(real).
 * Cover traffic adds Poisson-arrival decoys so the inter-arrival
 * distribution leaks nothing about the real traffic.
 */

import { useFetchJsonOnce } from "../hooks/useFetchJson";
import { FetchError, Stat } from "./_shared";

interface Point {
  target_size: number;
  bandwidth_overhead_ratio: number;
  n_distinct_sizes_after: number;
  n_distinct_sizes_before: number;
}

interface Payload {
  available: boolean;
  algorithm?: string;
  n_messages?: number;
  mean_original_size?: number;
  curve?: Point[];
  cover_schedule_preview?: number[];
  cover_schedule_size?: number;
}

export function DefensePaddingChart() {
  const state = useFetchJsonOnce<Payload>("/defenses/padding/demo");
  const data = state.kind === "data" ? state.value : undefined;

  if (!data?.available || !data.curve) {
    if (state.kind === "error") return <FetchError message={state.message} />;
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {state.kind === "loading" ? "computing…" : "padding unavailable"}
      </div>
    );
  }

  const points = data.curve;
  const width = 560;
  const height = 150;
  const padLeft = 60;
  const padRight = 10;
  const padTop = 14;
  const padBottom = 26;
  const xMax = Math.max(...points.map((p) => p.target_size));
  const overhead = points.map((p) => p.bandwidth_overhead_ratio);
  const oMax = Math.max(...overhead, 1.0);
  const sx = (t: number) => padLeft + (t / xMax) * (width - padLeft - padRight);
  const sy = (v: number) => padTop + (1 - v / oMax) * (height - padTop - padBottom);

  const pathOverhead = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.target_size)},${sy(p.bandwidth_overhead_ratio)}`)
    .join(" ");

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "padding"} accent />
        <Stat label="n msgs" value={data.n_messages ?? 0} digits={0} />
        <Stat label="mean real size" value={data.mean_original_size ?? 0} digits={1} suffix="B" />
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        role="img"
        aria-label="target bucket size vs bandwidth overhead"
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
        <path d={pathOverhead} stroke="var(--color-penumbra-cyan)" strokeWidth={1.5} fill="none" />
        {points.map((p) => (
          <g key={p.target_size}>
            <circle
              cx={sx(p.target_size)}
              cy={sy(p.bandwidth_overhead_ratio)}
              r={2.5}
              fill="var(--color-penumbra-cyan)"
            />
            <text
              x={sx(p.target_size)}
              y={height - padBottom + 12}
              textAnchor="middle"
              fontSize={8}
              fill="var(--color-penumbra-dim)"
            >
              {p.target_size}
            </text>
          </g>
        ))}
        <text x={6} y={padTop + 6} fontSize={8} fill="var(--color-penumbra-cyan)">
          bandwidth overhead × (lower better)
        </text>
      </svg>

      <div className="grid grid-cols-5 gap-1 text-[9px]">
        {points.map((p) => (
          <Stat
            key={p.target_size}
            label={`tgt ${p.target_size}B`}
            value={p.bandwidth_overhead_ratio}
            digits={2}
            suffix="×"
            caption={`sizes: ${p.n_distinct_sizes_after}`}
          />
        ))}
      </div>

      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        cover-traffic schedule (Poisson, first 20 offsets)
      </div>
      <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-2 text-[10px] text-[color:var(--color-penumbra-text)] break-all">
        {(data.cover_schedule_preview ?? []).join(" · ") || "—"}
      </div>
      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Schedule length {data.cover_schedule_size ?? 0}. Inter-arrival ∼ Exp(rate) so the visible
        packet stream is indistinguishable from any other Poisson source — the standard mix-net
        analysis (Loopix) requires Poisson arrivals to bound the linkability advantage.
      </div>
    </div>
  );
}
