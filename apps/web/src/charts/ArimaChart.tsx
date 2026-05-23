/**
 * ARIMA forecast band — history series + next-step point + 95% PI.
 *
 * Renders the recent series as a polyline, then the forecast point
 * at index n + 1 with a vertical ±1.96σ error bar and a wedge band
 * extending forward from the last observed point.
 */

import type { ArimaForecast } from "../streams/dashboard";
import { Stat } from "./_shared";

interface Props {
  data: ArimaForecast;
  width?: number;
  height?: number;
}

const M = { top: 14, right: 60, bottom: 26, left: 50 };

export function ArimaChart({ data, width = 560, height = 320 }: Props) {
  const { history, next_value, next_std } = data;
  if (history.length < 5) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        not enough history
      </div>
    );
  }

  const all = [...history, next_value];
  const yMin = Math.min(...all, next_value - 2 * next_std);
  const yMax = Math.max(...all, next_value + 2 * next_std);
  const span = yMax - yMin || 1;
  const yLo = yMin - span * 0.06;
  const yHi = yMax + span * 0.06;

  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  // X axis spans history.length + 1 sample points (one beyond for the forecast).
  const totalSteps = history.length + 1;
  const sx = (i: number) => M.left + (i / (totalSteps - 1)) * plotW;
  const sy = (v: number) => M.top + (1 - (v - yLo) / (yHi - yLo)) * plotH;

  const historyPoly = history.map((v, i) => `${sx(i)},${sy(v)}`).join(" ");
  const lastIdx = history.length - 1;
  const lastVal = history[lastIdx] as number;

  const yTicks = Array.from({ length: 5 }, (_, i) => yLo + (i / 4) * (yHi - yLo));

  return (
    <div className="font-mono">
      <svg
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="ARIMA forecast band"
      >
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
              {tv.toFixed(Math.abs(tv) >= 100 ? 0 : 2)}
            </text>
          </g>
        ))}
        {/* History polyline */}
        <polyline
          points={historyPoly}
          fill="none"
          stroke="var(--color-penumbra-text)"
          strokeWidth={1.3}
        />
        {/* Wedge band from last observed to forecast (PI band). */}
        <polygon
          points={`${sx(lastIdx)},${sy(lastVal)} ${sx(lastIdx + 1)},${sy(next_value + 1.96 * next_std)} ${sx(lastIdx + 1)},${sy(next_value - 1.96 * next_std)}`}
          fill="color-mix(in srgb, var(--color-penumbra-cyan) 22%, transparent)"
          stroke="none"
        />
        {/* Forecast line segment */}
        <line
          x1={sx(lastIdx)}
          y1={sy(lastVal)}
          x2={sx(lastIdx + 1)}
          y2={sy(next_value)}
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={1.6}
          strokeDasharray="4 2"
        />
        {/* Forecast point + vertical error bar */}
        <line
          x1={sx(lastIdx + 1)}
          y1={sy(next_value - 1.96 * next_std)}
          x2={sx(lastIdx + 1)}
          y2={sy(next_value + 1.96 * next_std)}
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={1.4}
        />
        <circle
          cx={sx(lastIdx + 1)}
          cy={sy(next_value)}
          r={3.5}
          fill="var(--color-penumbra-cyan)"
        />
        {/* Axis labels */}
        <text x={M.left} y={height - 8} fontSize={9} fill="var(--color-penumbra-muted)">
          t-{history.length}
        </text>
        <text
          x={M.left + plotW}
          y={height - 8}
          fontSize={9}
          textAnchor="end"
          fill="var(--color-penumbra-cyan)"
        >
          forecast
        </text>
      </svg>
      <div className="mt-2 grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="next ŷ" value={next_value} digits={3} accent />
        <Stat label="σ" value={next_std} digits={3} />
        <Stat label="95% PI" value={1.96 * next_std} digits={3} caption="± half-width" />
      </div>
    </div>
  );
}
