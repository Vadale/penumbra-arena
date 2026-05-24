/**
 * Full-size time-series line chart with axes.
 *
 * Used by DetailModal to render the full history of any metric.
 * Computes axis ticks dynamically, supports a hover tooltip that
 * shows the exact value at the closest sample, and renders min /
 * max / mean / std stats below the chart.
 *
 * Now also supports a drag-to-select brush (see useBrushSelection):
 * dragging across the chart highlights a window of samples and
 * recomputes the summary stats from that slice; "× clear selection"
 * resets.
 */

import { useMemo, useRef, useState } from "react";
import { useBrushSelection, windowStats } from "../hooks/useBrushSelection";
import { BrushStatsCard, Stat } from "./_shared";

interface Props {
  values: number[];
  label: string;
  yUnit?: string;
  width?: number;
  height?: number;
}

interface MarginBox {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

const M: MarginBox = { top: 12, right: 16, bottom: 24, left: 44 };

export function LineChart({ values, label, yUnit, width = 560, height = 280 }: Props) {
  const finite = values.filter((v) => Number.isFinite(v));
  const fullStats = useMemo(() => {
    if (finite.length === 0) return null;
    const sorted = [...finite].sort((a, b) => a - b);
    const min = sorted[0] as number;
    const max = sorted[sorted.length - 1] as number;
    const mean = finite.reduce((s, v) => s + v, 0) / finite.length;
    const variance = finite.reduce((s, v) => s + (v - mean) ** 2, 0) / finite.length;
    return { min, max, mean, std: Math.sqrt(variance), n: finite.length };
  }, [finite]);

  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;

  // Index-domain brush (data x = sample index in `values`).
  const lastIdx = Math.max(values.length - 1, 1);
  const sxIdx = (i: number) => M.left + (i / lastIdx) * plotW;
  const invertIdx = (px: number): number => {
    const norm = (px - M.left) / plotW;
    const clamped = Math.max(0, Math.min(1, norm));
    return Math.round(clamped * lastIdx);
  };

  const { range, clear, overlay } = useBrushSelection<number>(svgRef, sxIdx, invertIdx, {
    x: M.left,
    y: M.top,
    width: plotW,
    height: plotH,
  });

  const slicedValues = useMemo(() => {
    if (range === null) return values;
    const lo = Math.max(0, Math.min(values.length, range.start));
    const hi = Math.max(0, Math.min(values.length, range.end + 1));
    return values.slice(lo, hi);
  }, [range, values]);

  const slicedStats = useMemo(() => windowStats(slicedValues), [slicedValues]);

  if (fullStats === null || values.length < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        not enough samples yet
      </div>
    );
  }

  const span = fullStats.max - fullStats.min || 1;
  const yMin = fullStats.min - span * 0.05;
  const yMax = fullStats.max + span * 0.05;
  const yRange = yMax - yMin;
  const xStep = plotW / (values.length - 1);

  const points = values.map((v, i) => {
    const x = M.left + i * xStep;
    const norm = Number.isFinite(v) ? (v - yMin) / yRange : 0;
    const y = M.top + (1 - norm) * plotH;
    return [x, y, v] as const;
  });

  const polyline = points.map(([x, y]) => `${x},${y}`).join(" ");
  const first = points[0];
  const last = points[points.length - 1];
  const fillPath =
    first && last
      ? `M ${first[0]},${M.top + plotH} ` +
        points.map(([x, y]) => `L ${x},${y}`).join(" ") +
        ` L ${last[0]},${M.top + plotH} Z`
      : "";

  // Y-axis ticks at 5 evenly-spaced positions.
  const yTicks = Array.from({ length: 5 }, (_, i) => yMin + (i / 4) * yRange);

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
    const relX = ((e.clientX - rect.left) / rect.width) * width;
    const idx = Math.max(0, Math.min(values.length - 1, Math.round((relX - M.left) / xStep)));
    setHoverIdx(idx);
  };

  const hoverPoint = hoverIdx !== null ? points[hoverIdx] : null;

  const displayStats = slicedStats ?? fullStats;

  return (
    <div className="font-mono">
      <svg
        ref={svgRef}
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        onMouseMove={onMove}
        onMouseLeave={() => setHoverIdx(null)}
        role="img"
        aria-label={`${label} time series`}
      >
        {/* y-axis ticks + gridlines */}
        {yTicks.map((tickV) => {
          const norm = (tickV - yMin) / yRange;
          const y = M.top + (1 - norm) * plotH;
          return (
            <g key={tickV}>
              <line
                x1={M.left}
                y1={y}
                x2={M.left + plotW}
                y2={y}
                stroke="var(--color-penumbra-border)"
                strokeWidth={0.4}
                strokeDasharray="2 3"
              />
              <text
                x={M.left - 4}
                y={y}
                textAnchor="end"
                dominantBaseline="central"
                fontSize={9}
                fill="var(--color-penumbra-muted)"
              >
                {tickV.toFixed(Math.abs(tickV) >= 100 ? 0 : 2)}
              </text>
            </g>
          );
        })}

        {/* x-axis labels: start, mid, end (using sample count, not time) */}
        <text
          x={M.left}
          y={M.top + plotH + 14}
          fontSize={9}
          textAnchor="start"
          fill="var(--color-penumbra-muted)"
        >
          t-{values.length - 1}
        </text>
        <text
          x={M.left + plotW}
          y={M.top + plotH + 14}
          fontSize={9}
          textAnchor="end"
          fill="var(--color-penumbra-muted)"
        >
          now
        </text>

        {/* fill + line */}
        <path d={fillPath} fill="color-mix(in srgb, var(--color-penumbra-cyan) 14%, transparent)" />
        <polyline
          points={polyline}
          fill="none"
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={1.4}
        />

        {/* hover marker */}
        {hoverPoint && (
          <>
            <line
              x1={hoverPoint[0]}
              y1={M.top}
              x2={hoverPoint[0]}
              y2={M.top + plotH}
              stroke="var(--color-penumbra-text)"
              strokeWidth={0.6}
              strokeDasharray="2 2"
            />
            <circle
              cx={hoverPoint[0]}
              cy={hoverPoint[1]}
              r={3}
              fill="var(--color-penumbra-cyan)"
              stroke="var(--color-penumbra-bg)"
              strokeWidth={1}
            />
            <rect
              x={Math.min(hoverPoint[0] + 6, width - 86)}
              y={hoverPoint[1] - 14}
              width={80}
              height={18}
              fill="var(--color-penumbra-panel)"
              stroke="var(--color-penumbra-border)"
              strokeWidth={0.6}
            />
            <text
              x={Math.min(hoverPoint[0] + 10, width - 82)}
              y={hoverPoint[1] - 1}
              fontSize={10}
              fill="var(--color-penumbra-text)"
            >
              {hoverPoint[2].toFixed(3)}
              {yUnit ? ` ${yUnit}` : ""}
            </text>
          </>
        )}

        {overlay}
      </svg>

      {/* brush window summary */}
      <BrushStatsCard
        range={range}
        stats={slicedStats}
        onClear={clear}
        unit={yUnit}
        startLabel={range ? `idx=${range.start}` : undefined}
        endLabel={range ? `idx=${range.end}` : undefined}
      />

      {/* summary stats (slice if brushed, else full) */}
      <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="min" value={displayStats.min} digits="adaptive" />
        <Stat label="max" value={displayStats.max} digits="adaptive" />
        <Stat label="mean" value={displayStats.mean} digits="adaptive" />
        <Stat label="std" value={displayStats.std} digits="adaptive" />
      </div>
    </div>
  );
}
