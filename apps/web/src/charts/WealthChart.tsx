/**
 * Wealth distribution: Lorenz curve + Gini coefficient + percentile readout.
 *
 * The classic graphical inequality measure: cumulative population
 * share (x) vs cumulative wealth share (y). The straight 45° line
 * is perfect equality. Gini = 2 × area between Lorenz and equality.
 */

import type { WealthReport } from "../streams/dashboard";
import { Stat } from "./_shared";

interface Props {
  data: WealthReport;
  width?: number;
  height?: number;
}

const M = { top: 14, right: 16, bottom: 30, left: 50 };

export function WealthChart({ data, width = 480, height = 360 }: Props) {
  const { lorenz_x, lorenz_y, gini, p10, p50, p90, p99, total_wealth, n_agents } = data;
  if (lorenz_x.length < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        wealth warming up
      </div>
    );
  }
  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  const sx = (v: number) => M.left + v * plotW;
  const sy = (v: number) => M.top + (1 - v) * plotH;

  // Lorenz polygon: equality line (top) - lorenz curve (bottom).
  const lorenzPoly = lorenz_x.map((x, i) => `${sx(x)},${sy(lorenz_y[i] ?? 0)}`).join(" ");
  // Fill the area between the equality line and the Lorenz curve to
  // make the Gini area visually obvious.
  const giniPolygon = `${sx(0)},${sy(0)} ${lorenz_x
    .map((x, i) => `${sx(x)},${sy(lorenz_y[i] ?? 0)}`)
    .join(" ")} ${sx(1)},${sy(1)} ${sx(0)},${sy(0)}`;

  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="font-mono">
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Lorenz curve">
        {ticks.map((tv) => (
          <g key={`tick-${tv}`}>
            <line
              x1={M.left}
              y1={sy(tv)}
              x2={M.left + plotW}
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
            <text
              x={sx(tv)}
              y={M.top + plotH + 14}
              textAnchor="middle"
              fontSize={9}
              fill="var(--color-penumbra-muted)"
            >
              {tv.toFixed(2)}
            </text>
          </g>
        ))}
        {/* Gini area (between equality line and Lorenz curve) */}
        <polygon
          points={giniPolygon}
          fill="color-mix(in srgb, var(--color-penumbra-ember) 18%, transparent)"
        />
        {/* Equality line */}
        <line
          x1={sx(0)}
          y1={sy(0)}
          x2={sx(1)}
          y2={sy(1)}
          stroke="var(--color-penumbra-ember)"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
        {/* Lorenz curve */}
        <polyline
          points={lorenzPoly}
          fill="none"
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={1.7}
        />
        <text
          x={M.left + plotW / 2}
          y={height - 8}
          textAnchor="middle"
          fontSize={9}
          fill="var(--color-penumbra-muted)"
        >
          cumulative agent share
        </text>
        <text
          x={M.left - 36}
          y={M.top + plotH / 2}
          fontSize={9}
          fill="var(--color-penumbra-muted)"
          transform={`rotate(-90, ${M.left - 36}, ${M.top + plotH / 2})`}
        >
          cumulative wealth share
        </text>
      </svg>
      <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="Gini" value={gini} digits={3} ember={gini > 0.45} accent={gini <= 0.45} />
        <Stat label="agents" value={n_agents} digits={0} />
        <Stat label="total wealth" value={total_wealth} digits={0} />
        <Stat label="median" value={p50} digits={2} accent />
      </div>
      <div className="mt-1 grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="p10" value={p10} digits={2} />
        <Stat label="p50" value={p50} digits={2} />
        <Stat label="p90" value={p90} digits={2} accent />
        <Stat label="p99" value={p99} digits={2} ember />
      </div>
    </div>
  );
}
