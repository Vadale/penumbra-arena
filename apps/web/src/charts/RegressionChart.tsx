/**
 * Scatter + OLS fit + 95% confidence band.
 *
 * Renders the backend's RegressionResult: each (x_i, y_i) as a dot,
 * the fitted line ŷ = α + β·x overlaid, a shaded band of width
 * 1.96·σ around the line for a rough 95% prediction band, and the
 * key indices below (slope, intercept, R², σ, n).
 */

import type { RegressionFit } from "../streams/dashboard";

interface Props {
  fit: RegressionFit;
  /** Q-Q plot points (theoretical, sample) for the same fit's residuals. */
  qqPoints?: [number, number][];
  /** Residual-vs-fitted scatter — (fitted, residual) per sample. */
  residualVsFitted?: [number, number][];
  width?: number;
  height?: number;
}

const M = { top: 12, right: 16, bottom: 30, left: 50 };

export function RegressionChart({
  fit,
  qqPoints,
  residualVsFitted,
  width = 560,
  height = 320,
}: Props) {
  const { points, slope, intercept, r_squared, n, sigma } = fit;
  if (points.length < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        not enough samples yet
      </div>
    );
  }

  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const span = yMax - yMin || 1;
  const yLo = yMin - span * 0.08;
  const yHi = yMax + span * 0.08;

  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  const sx = (x: number) => M.left + ((x - xMin) / (xMax - xMin || 1)) * plotW;
  const sy = (y: number) => M.top + (1 - (y - yLo) / (yHi - yLo)) * plotH;

  // Fit line endpoints + 1.96σ confidence band.
  const fitY = (x: number) => intercept + slope * x;
  const lineX0 = sx(xMin);
  const lineY0 = sy(fitY(xMin));
  const lineX1 = sx(xMax);
  const lineY1 = sy(fitY(xMax));
  const halfBand = 1.96 * sigma;

  const bandPath = (() => {
    const STEPS = 24;
    const top: [number, number][] = [];
    const bot: [number, number][] = [];
    for (let i = 0; i <= STEPS; i++) {
      const x = xMin + (i / STEPS) * (xMax - xMin);
      const cx = sx(x);
      const upper = sy(fitY(x) + halfBand);
      const lower = sy(fitY(x) - halfBand);
      top.push([cx, upper]);
      bot.push([cx, lower]);
    }
    bot.reverse();
    return [...top.map(([x, y]) => `${x},${y}`), ...bot.map(([x, y]) => `${x},${y}`)].join(" ");
  })();

  // Y-axis ticks.
  const yTicks = Array.from({ length: 5 }, (_, i) => yLo + (i / 4) * (yHi - yLo));

  return (
    <div className="font-mono">
      <svg
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="regression scatter with OLS fit"
      >
        {yTicks.map((tv) => {
          const y = sy(tv);
          return (
            <g key={tv}>
              <line
                x1={M.left}
                y1={y}
                x2={width - M.right}
                y2={y}
                stroke="var(--color-penumbra-border)"
                strokeWidth={0.4}
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
        {/* 95% CI band */}
        <polygon
          points={bandPath}
          fill="color-mix(in srgb, var(--color-penumbra-cyan) 13%, transparent)"
          stroke="none"
        />
        {/* fit line */}
        <line
          x1={lineX0}
          y1={lineY0}
          x2={lineX1}
          y2={lineY1}
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={1.6}
        />
        {/* scatter */}
        {points.map(([x, y]) => (
          <circle
            key={`pt-${x}-${y.toFixed(4)}`}
            cx={sx(x)}
            cy={sy(y)}
            r={2.4}
            fill="var(--color-penumbra-text)"
            opacity={0.78}
          />
        ))}
        {/* x-axis labels */}
        <text
          x={M.left}
          y={height - M.bottom + 14}
          fontSize={9}
          textAnchor="start"
          fill="var(--color-penumbra-muted)"
        >
          t={xMin}
        </text>
        <text
          x={width - M.right}
          y={height - M.bottom + 14}
          fontSize={9}
          textAnchor="end"
          fill="var(--color-penumbra-muted)"
        >
          t={xMax}
        </text>
      </svg>

      {qqPoints && qqPoints.length >= 5 && (
        <div className="mt-3">
          <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
            Q-Q plot of residuals (vs N(0, 1))
          </div>
          <QQPlot points={qqPoints} />
        </div>
      )}

      {residualVsFitted && residualVsFitted.length >= 5 && (
        <div className="mt-3">
          <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
            residual vs fitted — heteroscedasticity / non-linearity check
          </div>
          <ResidualVsFitted points={residualVsFitted} />
        </div>
      )}

      <div className="mt-2 grid grid-cols-5 gap-2 text-[10px]">
        <Stat label="slope β" value={slope} digits={4} accent />
        <Stat label="intercept α" value={intercept} digits={2} />
        <Stat label="R²" value={r_squared} digits={3} accent />
        <Stat label="σ resid" value={sigma} digits={3} />
        <Stat label="n" value={n} digits={0} />
      </div>
    </div>
  );
}

function ResidualVsFitted({ points }: { points: [number, number][] }) {
  const w = 560;
  const h = 150;
  const inset = { top: 8, right: 8, bottom: 18, left: 36 };
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yAbs = Math.max(...ys.map((v) => Math.abs(v)), 1e-9);
  const yMin = -yAbs * 1.15;
  const yMax = yAbs * 1.15;
  const sx = (v: number) =>
    inset.left + ((v - xMin) / (xMax - xMin || 1)) * (w - inset.left - inset.right);
  const sy = (v: number) =>
    inset.top + (1 - (v - yMin) / (yMax - yMin || 1)) * (h - inset.top - inset.bottom);
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="residual vs fitted scatter">
      <line
        x1={sx(xMin)}
        y1={sy(0)}
        x2={sx(xMax)}
        y2={sy(0)}
        stroke="var(--color-penumbra-ember)"
        strokeWidth={0.8}
        strokeDasharray="3 3"
      />
      {points.map(([fv, rv]) => (
        <circle
          key={`rvf-${fv.toFixed(4)}-${rv.toFixed(4)}`}
          cx={sx(fv)}
          cy={sy(rv)}
          r={1.8}
          fill="var(--color-penumbra-cyan)"
          opacity={0.75}
        />
      ))}
      <text x={inset.left} y={h - 4} fontSize={9} fill="var(--color-penumbra-muted)">
        fitted ŷ
      </text>
      <text
        x={w - inset.right}
        y={h - 4}
        fontSize={9}
        textAnchor="end"
        fill="var(--color-penumbra-muted)"
      >
        ε = y − ŷ
      </text>
    </svg>
  );
}

function QQPlot({ points }: { points: [number, number][] }) {
  const w = 560;
  const h = 160;
  const inset = { top: 8, right: 8, bottom: 18, left: 28 };
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const xMin = Math.min(...xs, -3);
  const xMax = Math.max(...xs, 3);
  const yMin = Math.min(...ys, xMin);
  const yMax = Math.max(...ys, xMax);
  const sx = (v: number) =>
    inset.left + ((v - xMin) / (xMax - xMin || 1)) * (w - inset.left - inset.right);
  const sy = (v: number) =>
    inset.top + (1 - (v - yMin) / (yMax - yMin || 1)) * (h - inset.top - inset.bottom);
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Q-Q plot of residuals">
      {/* 45° reference line */}
      <line
        x1={sx(Math.max(xMin, yMin))}
        y1={sy(Math.max(xMin, yMin))}
        x2={sx(Math.min(xMax, yMax))}
        y2={sy(Math.min(xMax, yMax))}
        stroke="var(--color-penumbra-ember)"
        strokeWidth={0.8}
        strokeDasharray="3 3"
      />
      {points.map(([tx, sv]) => (
        <circle
          key={`qq-${tx.toFixed(4)}-${sv.toFixed(4)}`}
          cx={sx(tx)}
          cy={sy(sv)}
          r={1.8}
          fill="var(--color-penumbra-cyan)"
          opacity={0.75}
        />
      ))}
      <text x={inset.left} y={h - 4} fontSize={9} fill="var(--color-penumbra-muted)">
        theoretical (N(0,1))
      </text>
      <text
        x={w - inset.right}
        y={h - 4}
        fontSize={9}
        textAnchor="end"
        fill="var(--color-penumbra-muted)"
      >
        sample residuals
      </text>
    </svg>
  );
}

function Stat({
  label,
  value,
  digits,
  accent,
}: {
  label: string;
  value: number;
  digits: number;
  accent?: boolean;
}) {
  const display = digits === 0 ? value.toFixed(0) : value.toFixed(digits);
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
