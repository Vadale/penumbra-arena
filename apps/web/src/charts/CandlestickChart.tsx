/**
 * OHLC candlestick chart for the top-traded products.
 *
 * Each window of N ticks becomes one candle: body from open→close
 * (cyan if close ≥ open, ember otherwise), wick from low→high.
 *
 * Brush: drag inside the plot to pin a candle-index window. The
 * card below reports mean / std of `close` over that window plus the
 * matched candle count, so the user can spot regime changes inside a
 * long candle series.
 */

import { useMemo, useRef, useState } from "react";
import { useBrushSelection, windowStats } from "../hooks/useBrushSelection";
import type { CandleSeries } from "../streams/dashboard";
import { BrushStatsCard, Stat } from "./_shared";

interface Props {
  series: CandleSeries[];
  width?: number;
  height?: number;
}

const M = { top: 14, right: 16, bottom: 26, left: 50 };

export function CandlestickChart({ series, width = 560, height = 320 }: Props) {
  const [selectedPid, setSelectedPid] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const active = series.find((s) => s.product_id === selectedPid) ?? series[0];
  const candles = active?.candles ?? [];

  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  const nCandles = candles.length;
  const sxIdx = (i: number) => M.left + ((i + 0.5) / Math.max(1, nCandles)) * plotW;
  const invertIdx = (px: number): number => {
    const norm = (px - M.left) / plotW;
    const clamped = Math.max(0, Math.min(1, norm));
    return Math.round(clamped * Math.max(0, nCandles - 1));
  };

  const { range, clear, overlay } = useBrushSelection<number>(svgRef, sxIdx, invertIdx, {
    x: M.left,
    y: M.top,
    width: plotW,
    height: plotH,
  });

  const slicedCloses = useMemo(() => {
    if (range === null) return candles.map((c) => c.close);
    const lo = Math.max(0, Math.min(nCandles, range.start));
    const hi = Math.max(0, Math.min(nCandles, range.end + 1));
    return candles.slice(lo, hi).map((c) => c.close);
  }, [range, candles, nCandles]);

  const brushStats = useMemo(() => windowStats(slicedCloses), [slicedCloses]);

  if (series.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        no candles yet — market warming up
      </div>
    );
  }
  if (!active) {
    return null;
  }
  const { product_name, category, total_volume, bucket_ticks } = active;
  if (nCandles === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        no candles for {product_name}
      </div>
    );
  }

  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const yMin = Math.min(...lows);
  const yMax = Math.max(...highs);
  const span = yMax - yMin || 1;
  const yLo = yMin - span * 0.06;
  const yHi = yMax + span * 0.06;
  const sy = (v: number) => M.top + (1 - (v - yLo) / (yHi - yLo)) * plotH;
  const cellW = plotW / nCandles;
  const bodyW = Math.max(2, cellW * 0.65);

  const yTicks = Array.from({ length: 5 }, (_, i) => yLo + (i / 4) * (yHi - yLo));

  // Translate brushed candle indices into tick-bucket labels for the
  // stats card so the user sees the simulation-time window, not just
  // array indices.
  const startLabel = range
    ? `bucket=${candles[Math.max(0, Math.min(nCandles - 1, range.start))]?.bucket ?? range.start}`
    : undefined;
  const endLabel = range
    ? `bucket=${candles[Math.max(0, Math.min(nCandles - 1, range.end))]?.bucket ?? range.end}`
    : undefined;

  return (
    <div className="font-mono">
      {/* Product selector */}
      <div className="mb-2 flex flex-wrap gap-1 text-[10px]">
        {series.map((s) => (
          <button
            key={s.product_id}
            type="button"
            onClick={() => {
              setSelectedPid(s.product_id);
              clear();
            }}
            className={
              s.product_id === active.product_id
                ? "border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-0.5 text-[color:var(--color-penumbra-cyan)]"
                : "border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-text)]"
            }
          >
            {s.product_name} · {s.total_volume}
          </button>
        ))}
      </div>

      <svg
        ref={svgRef}
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${product_name} candlestick`}
      >
        {/* Y axis ticks */}
        {yTicks.map((tv) => (
          <g key={`y-${tv.toFixed(4)}`}>
            <line
              x1={M.left}
              y1={sy(tv)}
              x2={width - M.right}
              y2={sy(tv)}
              stroke="var(--color-penumbra-border)"
              strokeWidth={0.35}
              strokeDasharray="2 3"
            />
            <text
              x={M.left - 6}
              y={sy(tv)}
              textAnchor="end"
              dominantBaseline="central"
              fontSize={9}
              fill="var(--color-penumbra-muted)"
            >
              {tv.toFixed(2)}
            </text>
          </g>
        ))}

        {candles.map((c, i) => {
          const x = sxIdx(i);
          const yOpen = sy(c.open);
          const yClose = sy(c.close);
          const isUp = c.close >= c.open;
          const color = isUp ? "var(--color-penumbra-cyan)" : "var(--color-penumbra-ember)";
          const bodyTop = Math.min(yOpen, yClose);
          const bodyHeight = Math.max(1, Math.abs(yClose - yOpen));
          return (
            <g key={`candle-${c.bucket}`}>
              {/* wick */}
              <line x1={x} y1={sy(c.high)} x2={x} y2={sy(c.low)} stroke={color} strokeWidth={1} />
              {/* body */}
              <rect
                x={x - bodyW / 2}
                y={bodyTop}
                width={bodyW}
                height={bodyHeight}
                fill={isUp ? color : "var(--color-penumbra-bg)"}
                stroke={color}
                strokeWidth={1}
              />
            </g>
          );
        })}

        {/* X-axis ticks (first + last bucket) */}
        <text x={M.left} y={height - 8} fontSize={9} fill="var(--color-penumbra-muted)">
          t = {candles[0]?.bucket}
        </text>
        <text
          x={M.left + plotW}
          y={height - 8}
          textAnchor="end"
          fontSize={9}
          fill="var(--color-penumbra-muted)"
        >
          t = {candles[candles.length - 1]?.bucket}
        </text>
        {overlay}
      </svg>

      <BrushStatsCard
        range={range}
        stats={brushStats}
        onClear={clear}
        unit="price"
        startLabel={startLabel}
        endLabel={endLabel}
        countLabel="candles"
      />

      <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="product" value={product_name} />
        <Stat label="category" value={category} />
        <Stat label="bucket ticks" value={bucket_ticks.toString()} />
        <Stat label="volume" value={total_volume.toLocaleString()} accent />
      </div>
    </div>
  );
}
