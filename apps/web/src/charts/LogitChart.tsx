/**
 * Logistic regression curve + propensity score scatter.
 *
 * The sigmoid σ(α + β·x) is drawn across the feature range; the
 * scatter underneath shows observed (x, y) with treated points (y=1)
 * at the top edge and untreated (y=0) at the bottom. Pseudo-R² + n
 * shown as stats.
 */

import type { LogitResult } from "../streams/dashboard";
import { Stat } from "./_shared";

interface Props {
  data: LogitResult;
  width?: number;
  height?: number;
}

const M = { top: 14, right: 16, bottom: 30, left: 50 };

export function LogitChart({ data, width = 560, height = 320 }: Props) {
  const { intercept, slope, curve, points, n, pseudo_r2 } = data;
  if (curve.length < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        logit warming up
      </div>
    );
  }

  const xs = curve.map((p) => p[0]);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  const sx = (x: number) => M.left + ((x - xMin) / (xMax - xMin || 1)) * plotW;
  const sy = (y: number) => M.top + (1 - y) * plotH;

  const sigmoidPoly = curve.map(([x, y]) => `${sx(x)},${sy(y)}`).join(" ");

  // Threshold: x at which σ = 0.5 ⇒ x = -α/β.
  const xThreshold = slope !== 0 ? -intercept / slope : null;

  const yTicks = [0, 0.25, 0.5, 0.75, 1.0];
  const xTicks = Array.from({ length: 5 }, (_, i) => xMin + (i / 4) * (xMax - xMin));

  return (
    <div className="font-mono">
      <svg
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="logistic regression"
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
        {/* Scatter: treated (y=1) at top, untreated at bottom, jittered horizontally. */}
        {points.map(([x, y]) => (
          <circle
            key={`pt-${x.toFixed(4)}-${y}`}
            cx={sx(x)}
            cy={y === 1 ? M.top + plotH * 0.06 : M.top + plotH * 0.94}
            r={1.6}
            fill={y === 1 ? "var(--color-penumbra-cyan)" : "var(--color-penumbra-ember)"}
            opacity={0.55}
          />
        ))}
        {/* Threshold line at p = 0.5 */}
        {xThreshold !== null && xThreshold >= xMin && xThreshold <= xMax && (
          <>
            <line
              x1={sx(xThreshold)}
              y1={M.top}
              x2={sx(xThreshold)}
              y2={M.top + plotH}
              stroke="var(--color-penumbra-text)"
              strokeWidth={0.7}
              strokeDasharray="3 3"
              opacity={0.5}
            />
            <text
              x={sx(xThreshold) + 4}
              y={M.top + 10}
              fontSize={9}
              fill="var(--color-penumbra-muted)"
            >
              p = 0.5
            </text>
          </>
        )}
        {/* Sigmoid curve */}
        <polyline
          points={sigmoidPoly}
          fill="none"
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={1.7}
        />
        {/* X labels */}
        {xTicks.map((tv) => (
          <text
            key={`x${tv.toFixed(3)}`}
            x={sx(tv)}
            y={height - M.bottom + 14}
            textAnchor="middle"
            fontSize={9}
            fill="var(--color-penumbra-muted)"
          >
            {tv.toFixed(1)}
          </text>
        ))}
        <text
          x={width / 2}
          y={height - 6}
          textAnchor="middle"
          fontSize={9}
          fill="var(--color-penumbra-muted)"
        >
          x = trajectory norm at t-1
        </text>
      </svg>
      <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="α intercept" value={intercept} digits={3} />
        <Stat label="β slope" value={slope} digits={4} accent />
        <Stat label="pseudo R²" value={pseudo_r2} digits={3} accent />
        <Stat label="n" value={n} digits={0} />
      </div>
    </div>
  );
}
