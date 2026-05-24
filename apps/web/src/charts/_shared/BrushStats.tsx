/**
 * BrushStats — small stats card for a brushed time-series window.
 *
 * Concept taught: separation of concerns between selection (the brush
 * hook) and presentation (this component). Charts that opt into the
 * brush wire this card in below their SVG with the filtered slice
 * and the active range; the user gets "Window: tick A..B · mean=…
 * std=… n=…" plus a "Clear selection" button without each chart
 * re-implementing the same five lines of JSX.
 */

import type { WindowStats } from "../../hooks/useBrushSelection";

export interface BrushStatsCardProps {
  range: { start: number; end: number } | null;
  stats: WindowStats | null;
  onClear: () => void;
  unit?: string;
  startLabel?: string;
  endLabel?: string;
  /** Custom suffix shown after the n=… token (e.g. "iterations"). */
  countLabel?: string;
}

function fmt(v: number): string {
  const abs = Math.abs(v);
  if (!Number.isFinite(v)) return String(v);
  if (abs >= 1000) return v.toFixed(0);
  if (abs >= 10) return v.toFixed(2);
  return v.toFixed(3);
}

export function BrushStatsCard({
  range,
  stats,
  onClear,
  unit,
  startLabel,
  endLabel,
  countLabel = "samples",
}: BrushStatsCardProps) {
  if (range === null) {
    return (
      <div className="mt-2 flex items-center gap-2 text-[10px] text-[color:var(--color-penumbra-dim)]">
        <span className="uppercase tracking-wider">brush</span>
        <span>drag inside the chart to select a window</span>
      </div>
    );
  }
  const u = unit ? ` ${unit}` : "";
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px]">
      <span className="uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]">
        window
      </span>
      <span className="tabular-nums text-[color:var(--color-penumbra-text)]">
        {startLabel ?? `start=${fmt(range.start)}`} · {endLabel ?? `end=${fmt(range.end)}`}
      </span>
      {stats !== null ? (
        <span className="tabular-nums text-[color:var(--color-penumbra-muted)]">
          mean={fmt(stats.mean)}
          {u} · std={fmt(stats.std)}
          {u} · min={fmt(stats.min)} · max={fmt(stats.max)} · n={stats.n} {countLabel}
        </span>
      ) : (
        <span className="text-[color:var(--color-penumbra-dim)]">no samples in window</span>
      )}
      <button
        type="button"
        onClick={onClear}
        className="ml-auto border border-[color:var(--color-penumbra-cyan)] px-2 py-0.5 uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] hover:bg-[color:var(--color-penumbra-cyan)] hover:text-[color:var(--color-penumbra-bg)]"
        aria-label="Clear selection"
      >
        × clear selection
      </button>
    </div>
  );
}
