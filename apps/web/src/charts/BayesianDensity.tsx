/**
 * Beta posterior density curve + 95% credible interval band + mean marker.
 */

import type { BayesianPosterior } from "../streams/dashboard";

interface Props {
  data: BayesianPosterior;
  width?: number;
  height?: number;
}

const M = { top: 14, right: 16, bottom: 26, left: 50 };

export function BayesianDensity({ data, width = 560, height = 320 }: Props) {
  const { alpha, beta, mean, std, credible_low, credible_high, curve } = data;
  if (curve.length < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        posterior warming up
      </div>
    );
  }

  const xs = curve.map((p) => p[0]);
  const ys = curve.map((p) => p[1]);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMax = Math.max(...ys) * 1.1;

  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  const sx = (x: number) => M.left + ((x - xMin) / (xMax - xMin || 1)) * plotW;
  const sy = (y: number) => M.top + (1 - y / yMax) * plotH;

  // Build PDF polyline + fill area to baseline.
  const linePoly = curve.map(([x, y]) => `${sx(x)},${sy(y)}`).join(" ");
  // Subset of points inside the credible interval, for shading.
  const inside = curve.filter(([x]) => x >= credible_low && x <= credible_high);
  const ciFill = (() => {
    if (inside.length < 2) return "";
    const top = inside.map(([x, y]) => `${sx(x)},${sy(y)}`);
    const first = inside[0] as [number, number];
    const last = inside[inside.length - 1] as [number, number];
    return `${sx(first[0])},${sy(0)} ${top.join(" ")} ${sx(last[0])},${sy(0)}`;
  })();

  const xTicks = [0, 0.25, 0.5, 0.75, 1.0];

  return (
    <div className="font-mono">
      <svg
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="bayesian posterior"
      >
        {/* baseline */}
        <line
          x1={M.left}
          y1={sy(0)}
          x2={M.left + plotW}
          y2={sy(0)}
          stroke="var(--color-penumbra-border)"
          strokeWidth={0.4}
        />
        {/* 95% credible interval fill */}
        {ciFill && (
          <polygon
            points={ciFill}
            fill="color-mix(in srgb, var(--color-penumbra-cyan) 22%, transparent)"
          />
        )}
        {/* PDF curve */}
        <polyline
          points={linePoly}
          fill="none"
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={1.8}
        />
        {/* mean marker */}
        <line
          x1={sx(mean)}
          y1={M.top}
          x2={sx(mean)}
          y2={M.top + plotH}
          stroke="var(--color-penumbra-text)"
          strokeWidth={1}
          strokeDasharray="4 3"
        />
        <text x={sx(mean) + 4} y={M.top + 10} fontSize={9} fill="var(--color-penumbra-muted)">
          mean = {mean.toFixed(3)}
        </text>
        {/* CI bounds */}
        <line
          x1={sx(credible_low)}
          y1={M.top + plotH * 0.8}
          x2={sx(credible_low)}
          y2={M.top + plotH}
          stroke="var(--color-penumbra-ember)"
          strokeWidth={1}
        />
        <line
          x1={sx(credible_high)}
          y1={M.top + plotH * 0.8}
          x2={sx(credible_high)}
          y2={M.top + plotH}
          stroke="var(--color-penumbra-ember)"
          strokeWidth={1}
        />
        {/* X labels */}
        {xTicks.map((tv) => (
          <text
            key={`x${tv}`}
            x={sx(tv)}
            y={height - M.bottom + 14}
            textAnchor="middle"
            fontSize={9}
            fill="var(--color-penumbra-muted)"
          >
            {tv.toFixed(2)}
          </text>
        ))}
        <text
          x={width / 2}
          y={height - 6}
          textAnchor="middle"
          fontSize={9}
          fill="var(--color-penumbra-muted)"
        >
          θ — probability the metric is "high"
        </text>
      </svg>
      <div className="mt-2 grid grid-cols-5 gap-2 text-[10px]">
        <Stat label="α" value={alpha} digits={1} />
        <Stat label="β" value={beta} digits={1} />
        <Stat label="mean" value={mean} digits={3} accent />
        <Stat label="std" value={std} digits={3} />
        <Stat
          label="95% CrI"
          value={credible_low}
          digits={3}
          caption={`–${credible_high.toFixed(3)}`}
        />
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  digits,
  accent,
  caption,
}: {
  label: string;
  value: number;
  digits: number;
  accent?: boolean;
  caption?: string;
}) {
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div
        className={`tabular-nums ${accent ? "text-[color:var(--color-penumbra-cyan)]" : "text-[color:var(--color-penumbra-text)]"}`}
      >
        {value.toFixed(digits)}
      </div>
      {caption ? (
        <div className="text-[8px] text-[color:var(--color-penumbra-dim)]">{caption}</div>
      ) : null}
    </div>
  );
}
