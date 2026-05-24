/**
 * CPI index + money supply over time.
 *
 * Twin-axis line chart: cyan = CPI (left axis), ember = money supply
 * (right axis). Lets you see if inflation tracks money supply or
 * decouples (it shouldn't, since our market conserves money — any
 * inflation is pure supply/demand on a fixed money base).
 *
 * Brush: drag inside the plot to limit the readout below to a tick
 * window — mean / std / range of CPI within the window are reported.
 */

import { useMemo, useRef } from "react";
import { useBrushSelection, windowStats } from "../hooks/useBrushSelection";
import type { InflationSeries } from "../streams/dashboard";
import { BrushStatsCard, Stat } from "./_shared";

interface Props {
  data: InflationSeries;
  width?: number;
  height?: number;
}

const M = { top: 14, right: 50, bottom: 30, left: 50 };

export function InflationChart({ data, width = 560, height = 320 }: Props) {
  const { cpi, money_supply, n_samples } = data;
  const svgRef = useRef<SVGSVGElement | null>(null);

  const ticks = cpi.map((p) => p[0]);
  const tMin = ticks.length ? Math.min(...ticks) : 0;
  const tMax = ticks.length ? Math.max(...ticks) : 0;
  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  const sx = (t: number) => M.left + ((t - tMin) / (tMax - tMin || 1)) * plotW;
  const invertX = (px: number): number => {
    const norm = (px - M.left) / plotW;
    const clamped = Math.max(0, Math.min(1, norm));
    return Math.round(tMin + clamped * (tMax - tMin));
  };

  const { range, clear, overlay } = useBrushSelection<number>(svgRef, sx, invertX, {
    x: M.left,
    y: M.top,
    width: plotW,
    height: plotH,
  });

  const windowCpi = useMemo(() => {
    if (range === null) return cpi.map((p) => p[1]);
    return cpi.filter(([t]) => t >= range.start && t <= range.end).map((p) => p[1]);
  }, [range, cpi]);

  const brushStats = useMemo(() => windowStats(windowCpi), [windowCpi]);

  if (cpi.length < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        inflation series warming up
      </div>
    );
  }
  const cpiVals = cpi.map((p) => p[1]);
  const moneyVals = money_supply.map((p) => p[1]);
  const cpiLo = Math.min(...cpiVals) * 0.98;
  const cpiHi = Math.max(...cpiVals) * 1.02;
  const moneyLo = Math.min(...moneyVals) * 0.99;
  const moneyHi = Math.max(...moneyVals) * 1.01;

  const syCpi = (v: number) => M.top + (1 - (v - cpiLo) / (cpiHi - cpiLo || 1)) * plotH;
  const syMoney = (v: number) => M.top + (1 - (v - moneyLo) / (moneyHi - moneyLo || 1)) * plotH;

  const cpiPoly = cpi.map(([t, v]) => `${sx(t)},${syCpi(v)}`).join(" ");
  const moneyPoly = money_supply.map(([t, v]) => `${sx(t)},${syMoney(v)}`).join(" ");

  const yTicksLeft = Array.from({ length: 5 }, (_, i) => cpiLo + (i / 4) * (cpiHi - cpiLo));
  const yTicksRight = Array.from({ length: 5 }, (_, i) => moneyLo + (i / 4) * (moneyHi - moneyLo));

  const cpiNow = cpiVals[cpiVals.length - 1] ?? 1;
  const cpiBase = cpiVals[0] ?? 1;
  const inflationPct = ((cpiNow - cpiBase) / cpiBase) * 100;

  return (
    <div className="font-mono">
      <svg
        ref={svgRef}
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="CPI + money supply"
      >
        {yTicksLeft.map((tv) => (
          <g key={`yL-${tv.toFixed(4)}`}>
            <line
              x1={M.left}
              y1={syCpi(tv)}
              x2={width - M.right}
              y2={syCpi(tv)}
              stroke="var(--color-penumbra-border)"
              strokeWidth={0.3}
              strokeDasharray="2 3"
            />
            <text
              x={M.left - 6}
              y={syCpi(tv)}
              textAnchor="end"
              dominantBaseline="central"
              fontSize={9}
              fill="var(--color-penumbra-cyan)"
            >
              {tv.toFixed(2)}
            </text>
          </g>
        ))}
        {yTicksRight.map((tv) => (
          <text
            key={`yR-${tv.toFixed(2)}`}
            x={width - M.right + 6}
            y={syMoney(tv)}
            dominantBaseline="central"
            fontSize={9}
            fill="var(--color-penumbra-ember)"
          >
            {tv.toFixed(0)}
          </text>
        ))}
        {/* CPI line */}
        <polyline
          points={cpiPoly}
          fill="none"
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={1.6}
        />
        {/* Money supply line */}
        <polyline
          points={moneyPoly}
          fill="none"
          stroke="var(--color-penumbra-ember)"
          strokeWidth={1.3}
          strokeDasharray="2 2"
        />
        <text x={M.left} y={height - 8} fontSize={9} fill="var(--color-penumbra-muted)">
          t = {tMin}
        </text>
        <text
          x={M.left + plotW}
          y={height - 8}
          textAnchor="end"
          fontSize={9}
          fill="var(--color-penumbra-muted)"
        >
          t = {tMax}
        </text>
        <text x={M.left + 6} y={M.top + 12} fontSize={9} fill="var(--color-penumbra-cyan)">
          CPI (left)
        </text>
        <text
          x={width - M.right - 6}
          y={M.top + 12}
          textAnchor="end"
          fontSize={9}
          fill="var(--color-penumbra-ember)"
        >
          money supply (right)
        </text>
        {overlay}
      </svg>
      <BrushStatsCard
        range={range}
        stats={brushStats}
        onClear={clear}
        unit="CPI"
        startLabel={range ? `tick=${range.start}` : undefined}
        endLabel={range ? `tick=${range.end}` : undefined}
        countLabel="ticks"
      />
      <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="CPI now" value={cpiNow} digits={3} accent />
        <Stat
          label="inflation %"
          value={inflationPct}
          digits={2}
          accent={inflationPct >= 0}
          ember={inflationPct < 0}
          caption={inflationPct >= 0 ? "inflation" : "deflation"}
        />
        <Stat label="money M" value={moneyVals[moneyVals.length - 1] ?? 0} digits={0} />
        <Stat label="samples" value={n_samples} digits={0} />
      </div>
    </div>
  );
}
