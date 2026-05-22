/**
 * Kaplan-Meier survival curve with 95% pointwise CI band.
 */

import type { SurvivalCurve } from "../streams/dashboard";

interface Props {
  data: SurvivalCurve;
  width?: number;
  height?: number;
}

const M = { top: 14, right: 16, bottom: 30, left: 50 };

export function SurvivalChart({ data, width = 560, height = 320 }: Props) {
  const { times, survival, confidence_low, confidence_high, n_events, n_censored, median_time } =
    data;
  if (times.length < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        not enough events yet
      </div>
    );
  }

  const tMin = 0;
  const tMax = times[times.length - 1] ?? 1;
  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  const sx = (t: number) => M.left + ((t - tMin) / (tMax - tMin || 1)) * plotW;
  const sy = (s: number) => M.top + (1 - s) * plotH;

  // Build a step polyline for the survival curve.
  const stepPts: string[] = [];
  let prevS = 1.0;
  stepPts.push(`${sx(tMin)},${sy(1)}`);
  for (let i = 0; i < times.length; i++) {
    const t = times[i] ?? 0;
    const s = survival[i] ?? prevS;
    stepPts.push(`${sx(t)},${sy(prevS)}`);
    stepPts.push(`${sx(t)},${sy(s)}`);
    prevS = s;
  }
  const stepPoly = stepPts.join(" ");

  // CI band as a step polygon.
  const upper: [number, number][] = [];
  const lower: [number, number][] = [];
  for (let i = 0; i < times.length; i++) {
    const t = times[i] ?? 0;
    upper.push([sx(t), sy(confidence_high[i] ?? 1)]);
    lower.push([sx(t), sy(confidence_low[i] ?? 0)]);
  }
  lower.reverse();
  const bandPoints = [
    ...upper.map(([x, y]) => `${x},${y}`),
    ...lower.map(([x, y]) => `${x},${y}`),
  ].join(" ");

  const yTicks = [0, 0.25, 0.5, 0.75, 1.0];

  return (
    <div className="font-mono">
      <svg
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="KM survival curve"
      >
        {yTicks.map((tv) => (
          <g key={`y${tv}`}>
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
        {/* 95% CI band */}
        <polygon
          points={bandPoints}
          fill="color-mix(in srgb, var(--color-penumbra-cyan) 14%, transparent)"
        />
        {/* survival step curve */}
        <polyline
          points={stepPoly}
          fill="none"
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={1.6}
        />
        {/* median marker */}
        {median_time !== null && (
          <>
            <line
              x1={sx(median_time)}
              y1={M.top}
              x2={sx(median_time)}
              y2={sy(0.5)}
              stroke="var(--color-penumbra-ember)"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            <text
              x={sx(median_time) + 4}
              y={M.top + 10}
              fontSize={9}
              fill="var(--color-penumbra-ember)"
            >
              median = {median_time.toFixed(0)}
            </text>
          </>
        )}
        <text x={M.left} y={height - 8} fontSize={9} fill="var(--color-penumbra-muted)">
          t = 0
        </text>
        <text
          x={M.left + plotW}
          y={height - 8}
          fontSize={9}
          textAnchor="end"
          fill="var(--color-penumbra-muted)"
        >
          t = {tMax} ticks
        </text>
      </svg>
      <div className="mt-2 grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="events" value={n_events} accent />
        <Stat label="censored" value={n_censored} />
        <Stat label="median" value={median_time ?? Number.NaN} />
      </div>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  const display = Number.isFinite(value) ? value.toFixed(value < 10 ? 2 : 0) : "—";
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div
        className={`tabular-nums ${accent ? "text-[color:var(--color-penumbra-cyan)]" : "text-[color:var(--color-penumbra-text)]"}`}
      >
        {display}
      </div>
    </div>
  );
}
