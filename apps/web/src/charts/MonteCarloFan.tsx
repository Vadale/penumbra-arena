/**
 * Bootstrap fan chart with VaR / CVaR markers.
 *
 * Visualises a Monte Carlo bootstrap distribution as a vertical fan:
 * a wide outer band [5th, 95th], a tighter inner band [25th, 75th],
 * and a thick median line. VaR(95) is marked on the right margin
 * as a red horizontal line.
 */

import type { MonteCarloFan as MCFan } from "../streams/dashboard";

interface Props {
  fan: MCFan;
  width?: number;
  height?: number;
}

const M = { top: 12, right: 32, bottom: 26, left: 50 };

export function MonteCarloFan({ fan, width = 560, height = 300 }: Props) {
  const p = fan.percentiles;
  const p5 = p["5"] as number;
  const p25 = p["25"] as number;
  const p50 = p["50"] as number;
  const p75 = p["75"] as number;
  const p95 = p["95"] as number;
  if ([p5, p25, p50, p75, p95].some((v) => v === undefined)) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        bootstrap warming up
      </div>
    );
  }

  const yMin = Math.min(p5, fan.var) * 0.96;
  const yMax = Math.max(p95, fan.cvar) * 1.04;
  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  const sy = (v: number) => M.top + (1 - (v - yMin) / (yMax - yMin || 1)) * plotH;

  // The "fan" is drawn as nested horizontal bands across the plot width.
  const bandX = M.left;
  const bandW = plotW;

  const yTicks = Array.from({ length: 5 }, (_, i) => yMin + (i / 4) * (yMax - yMin));

  return (
    <div className="font-mono">
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="monte carlo fan">
        {yTicks.map((tv) => {
          const y = sy(tv);
          return (
            <g key={`y${tv.toFixed(3)}`}>
              <line
                x1={M.left}
                y1={y}
                x2={M.left + plotW}
                y2={y}
                stroke="var(--color-penumbra-border)"
                strokeWidth={0.35}
                strokeDasharray="2 3"
              />
              <text
                x={M.left - 6}
                y={y}
                textAnchor="end"
                dominantBaseline="central"
                fontSize={9}
                fill="var(--color-penumbra-muted)"
              >
                {tv.toFixed(Math.abs(tv) >= 100 ? 0 : 2)}
              </text>
            </g>
          );
        })}

        {/* Outer band [5, 95]. */}
        <rect
          x={bandX}
          y={sy(p95)}
          width={bandW}
          height={Math.max(1, sy(p5) - sy(p95))}
          fill="color-mix(in srgb, var(--color-penumbra-cyan) 12%, transparent)"
        />
        {/* Inner band [25, 75]. */}
        <rect
          x={bandX}
          y={sy(p75)}
          width={bandW}
          height={Math.max(1, sy(p25) - sy(p75))}
          fill="color-mix(in srgb, var(--color-penumbra-cyan) 26%, transparent)"
        />
        {/* Median line. */}
        <line
          x1={bandX}
          y1={sy(p50)}
          x2={bandX + bandW}
          y2={sy(p50)}
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={1.8}
        />
        {/* VaR line (right side, ember). */}
        <line
          x1={bandX}
          y1={sy(fan.var)}
          x2={bandX + bandW}
          y2={sy(fan.var)}
          stroke="var(--color-penumbra-ember)"
          strokeWidth={1.2}
          strokeDasharray="4 3"
        />
        <text
          x={bandX + bandW + 4}
          y={sy(fan.var)}
          dominantBaseline="central"
          fontSize={9}
          fill="var(--color-penumbra-ember)"
        >
          VaR
        </text>
        {/* CVaR marker (tail mean). */}
        <line
          x1={bandX}
          y1={sy(fan.cvar)}
          x2={bandX + bandW}
          y2={sy(fan.cvar)}
          stroke="var(--color-penumbra-ember)"
          strokeWidth={0.7}
          strokeDasharray="2 4"
          opacity={0.7}
        />
        <text
          x={bandX + bandW + 4}
          y={sy(fan.cvar)}
          dominantBaseline="central"
          fontSize={9}
          fill="var(--color-penumbra-ember)"
          opacity={0.7}
        >
          CVaR
        </text>
      </svg>

      <div className="mt-2 grid grid-cols-5 gap-2 text-[10px]">
        <Stat label="p05" value={p5} />
        <Stat label="p50" value={p50} accent />
        <Stat label="p95" value={p95} />
        <Stat label="VaR.95" value={fan.var} ember />
        <Stat label="CVaR.95" value={fan.cvar} ember />
      </div>
      <div className="mt-1 text-[9px] text-[color:var(--color-penumbra-dim)]">
        bootstrap n = {fan.n_samples}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
  ember,
}: {
  label: string;
  value: number;
  accent?: boolean;
  ember?: boolean;
}) {
  const cls = ember
    ? "text-[color:var(--color-penumbra-ember)]"
    : accent
      ? "text-[color:var(--color-penumbra-cyan)]"
      : "text-[color:var(--color-penumbra-text)]";
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div className={`tabular-nums ${cls}`}>{value.toFixed(2)}</div>
    </div>
  );
}
