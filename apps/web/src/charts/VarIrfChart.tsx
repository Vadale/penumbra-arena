/**
 * VAR impulse-response grid.
 *
 * One small line plot per (shock series → response series) pair.
 * The grid is K×K (K = number of series); cell (i, j) shows how a
 * 1-σ shock in series i propagates into series j over `horizon` steps.
 */

import type { VARImpulseResponse } from "../streams/dashboard";

interface Props {
  data: VARImpulseResponse;
  width?: number;
}

export function VarIrfChart({ data, width = 560 }: Props) {
  const { series_names, irf, horizon, lag_order } = data;
  const K = series_names.length;
  if (K < 2 || irf.length < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        VAR fit warming up
      </div>
    );
  }

  const cellSize = (width - 60) / K;
  const totalHeight = cellSize * K + 60;

  // For each shock i, find the y-extent across the whole row so the
  // cells in a row share a scale.
  const rowExtents: { yMin: number; yMax: number }[] = [];
  for (let i = 0; i < K; i++) {
    let yMin = Number.POSITIVE_INFINITY;
    let yMax = Number.NEGATIVE_INFINITY;
    for (let step = 0; step < irf.length; step++) {
      for (let j = 0; j < K; j++) {
        const v = irf[step]?.[i]?.[j] ?? 0;
        if (v < yMin) yMin = v;
        if (v > yMax) yMax = v;
      }
    }
    const pad = (yMax - yMin || 1) * 0.1;
    rowExtents.push({ yMin: yMin - pad, yMax: yMax + pad });
  }

  return (
    <div className="font-mono">
      <svg
        viewBox={`0 0 ${width} ${totalHeight}`}
        width="100%"
        role="img"
        aria-label="VAR impulse responses grid"
      >
        {/* Column labels (response) */}
        {series_names.map((name, j) => (
          <text
            key={`col-${name}`}
            x={60 + (j + 0.5) * cellSize}
            y={20}
            textAnchor="middle"
            fontSize={10}
            fill="var(--color-penumbra-muted)"
          >
            → {name}
          </text>
        ))}
        {/* Row labels (shock) */}
        {series_names.map((name, i) => (
          <text
            key={`row-${name}`}
            x={50}
            y={40 + (i + 0.5) * cellSize}
            textAnchor="end"
            dominantBaseline="central"
            fontSize={10}
            fill="var(--color-penumbra-muted)"
          >
            shock {name}
          </text>
        ))}
        {/* Cells */}
        {Array.from({ length: K }, (_, i) =>
          Array.from({ length: K }, (_, j) => {
            const cellX = 60 + j * cellSize;
            const cellY = 30 + i * cellSize;
            const { yMin, yMax } = rowExtents[i] ?? { yMin: -1, yMax: 1 };
            const sx = (step: number) =>
              cellX + 4 + (step / Math.max(1, irf.length - 1)) * (cellSize - 8);
            const sy = (v: number) =>
              cellY + 4 + (1 - (v - yMin) / (yMax - yMin || 1)) * (cellSize - 8);
            const pts = irf.map((step, h) => `${sx(h)},${sy(step?.[i]?.[j] ?? 0)}`).join(" ");
            const cellKey = `${series_names[i] ?? i}-to-${series_names[j] ?? j}`;
            return (
              <g key={cellKey}>
                <rect
                  x={cellX + 2}
                  y={cellY + 2}
                  width={cellSize - 4}
                  height={cellSize - 4}
                  fill="var(--color-penumbra-bg)"
                  stroke="var(--color-penumbra-border)"
                  strokeWidth={0.4}
                />
                {/* zero line */}
                <line
                  x1={sx(0)}
                  y1={sy(0)}
                  x2={sx(irf.length - 1)}
                  y2={sy(0)}
                  stroke="var(--color-penumbra-dim)"
                  strokeWidth={0.4}
                  strokeDasharray="2 2"
                />
                <polyline
                  points={pts}
                  fill="none"
                  stroke={i === j ? "var(--color-penumbra-ember)" : "var(--color-penumbra-cyan)"}
                  strokeWidth={1.3}
                />
              </g>
            );
          }),
        )}
      </svg>
      <div className="mt-2 grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="series" value={K} digits={0} />
        <Stat label="lag order" value={lag_order} digits={0} accent />
        <Stat label="horizon" value={horizon} digits={0} />
      </div>
    </div>
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
    </div>
  );
}
