/**
 * GARCH(1, 1) conditional volatility chart.
 *
 * Shows the log-returns series + the σ_t conditional volatility
 * overlay. Parameters (ω, α, β, persistence) shown below.
 */

import type { GarchResult } from "../streams/dashboard";
import { Stat } from "./_shared";

interface Props {
  data: GarchResult;
  width?: number;
  height?: number;
}

const M = { top: 14, right: 40, bottom: 26, left: 50 };

export function GarchChart({ data, width = 560, height = 320 }: Props) {
  const { omega, alpha, beta, persistence, log_returns, conditional_volatility } = data;
  const n = Math.min(log_returns.length, conditional_volatility.length);
  if (n < 5) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        GARCH warming up
      </div>
    );
  }
  const returns = log_returns.slice(-n);
  const vol = conditional_volatility.slice(-n);
  const allVals = [...returns, ...vol, ...vol.map((v) => -v)];
  const yMin = Math.min(...allVals);
  const yMax = Math.max(...allVals);
  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  const sx = (i: number) => M.left + (i / Math.max(1, n - 1)) * plotW;
  const sy = (v: number) => M.top + (1 - (v - yMin) / (yMax - yMin || 1)) * plotH;

  const returnsPoly = returns.map((r, i) => `${sx(i)},${sy(r)}`).join(" ");
  const volPolyUpper = vol.map((v, i) => `${sx(i)},${sy(v)}`).join(" ");
  const volPolyLower = vol.map((v, i) => `${sx(i)},${sy(-v)}`).join(" ");
  // Band between ±σ_t
  const bandPts: string[] = [];
  for (let i = 0; i < n; i++) bandPts.push(`${sx(i)},${sy(vol[i] ?? 0)}`);
  for (let i = n - 1; i >= 0; i--) bandPts.push(`${sx(i)},${sy(-(vol[i] ?? 0))}`);

  const yTicks = Array.from({ length: 5 }, (_, i) => yMin + (i / 4) * (yMax - yMin));

  return (
    <div className="font-mono">
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="GARCH volatility">
        {yTicks.map((tv) => (
          <g key={`y${tv.toFixed(3)}`}>
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
        {/* ±σ_t band */}
        <polygon
          points={bandPts.join(" ")}
          fill="color-mix(in srgb, var(--color-penumbra-cyan) 14%, transparent)"
        />
        <polyline
          points={volPolyUpper}
          fill="none"
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={1.2}
        />
        <polyline
          points={volPolyLower}
          fill="none"
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={1.2}
        />
        {/* log-returns series */}
        <polyline
          points={returnsPoly}
          fill="none"
          stroke="var(--color-penumbra-text)"
          strokeWidth={0.9}
        />
        {/* zero line */}
        <line
          x1={M.left}
          y1={sy(0)}
          x2={width - M.right}
          y2={sy(0)}
          stroke="var(--color-penumbra-dim)"
          strokeWidth={0.5}
        />
      </svg>
      <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="ω" value={omega} digits={4} />
        <Stat label="α" value={alpha} digits={3} accent />
        <Stat label="β" value={beta} digits={3} accent />
        <Stat
          label="persist"
          value={persistence}
          digits={3}
          ember={persistence > 0.98}
          caption={persistence > 0.98 ? "near-unit-root" : ""}
        />
      </div>
    </div>
  );
}
