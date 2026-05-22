/**
 * Granger causality p-value heatmap.
 *
 * Renders a K×K matrix where cell[i, j] = p-value of the null
 * 'series i does NOT Granger-cause series j' at the chosen lag.
 * Low p-values shade cyan (causality); high p-values stay neutral.
 * Diagonal is dimmed.
 */

import type { GrangerMatrix as GrangerData } from "../streams/dashboard";

interface Props {
  data: GrangerData;
  width?: number;
  height?: number;
}

function pColor(p: number, isDiag: boolean): string {
  if (isDiag) return "rgba(50, 55, 64, 0.45)";
  if (!Number.isFinite(p) || p < 0) return "rgba(40, 45, 55, 0.5)";
  if (p < 0.01) return "color-mix(in srgb, var(--color-penumbra-cyan) 80%, transparent)";
  if (p < 0.05) return "color-mix(in srgb, var(--color-penumbra-cyan) 55%, transparent)";
  if (p < 0.1) return "color-mix(in srgb, var(--color-penumbra-cyan) 30%, transparent)";
  return "color-mix(in srgb, var(--color-penumbra-dim) 30%, transparent)";
}

export function GrangerMatrix({ data, width = 560, height = 360 }: Props) {
  const { series_names, p_values, max_lag, n_obs } = data;
  if (series_names.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        granger warming up
      </div>
    );
  }

  const K = series_names.length;
  const M = { top: 30, right: 20, bottom: 70, left: 70 };
  const grid = Math.min(width - M.left - M.right, height - M.top - M.bottom);
  const cell = grid / K;

  return (
    <div className="font-mono">
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="granger matrix">
        {/* Column labels (CAUSES) on top */}
        {series_names.map((name, j) => (
          <text
            key={`col-${name}`}
            x={M.left + (j + 0.5) * cell}
            y={M.top - 8}
            textAnchor="middle"
            fontSize={10}
            fill="var(--color-penumbra-muted)"
          >
            {name}
          </text>
        ))}
        <text
          x={M.left + (K * cell) / 2}
          y={M.top - 22}
          textAnchor="middle"
          fontSize={9}
          fill="var(--color-penumbra-dim)"
        >
          ROW Granger-causes COL (lower p = more causality)
        </text>

        {/* Row labels (CAUSED-BY) on left */}
        {series_names.map((name, i) => (
          <text
            key={`row-${name}`}
            x={M.left - 8}
            y={M.top + (i + 0.5) * cell}
            textAnchor="end"
            dominantBaseline="central"
            fontSize={10}
            fill="var(--color-penumbra-muted)"
          >
            {name}
          </text>
        ))}

        {/* Heatmap cells */}
        {p_values.map((row, i) =>
          row.map((p, j) => {
            const isDiag = i === j;
            return (
              <g key={`c-${series_names[i]}-${series_names[j]}`}>
                <rect
                  x={M.left + j * cell}
                  y={M.top + i * cell}
                  width={cell - 1}
                  height={cell - 1}
                  fill={pColor(p, isDiag)}
                  stroke="var(--color-penumbra-bg)"
                  strokeWidth={0.6}
                />
                {!isDiag && (
                  <text
                    x={M.left + (j + 0.5) * cell}
                    y={M.top + (i + 0.5) * cell}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={11}
                    fill={p < 0.05 ? "var(--color-penumbra-bg)" : "var(--color-penumbra-text)"}
                    fontWeight={p < 0.05 ? 700 : 400}
                  >
                    {p < 0.001 ? "<.001" : p.toFixed(3)}
                  </text>
                )}
              </g>
            );
          }),
        )}

        {/* Legend */}
        <g transform={`translate(${M.left}, ${M.top + K * cell + 18})`}>
          <text fontSize={9} fill="var(--color-penumbra-dim)">
            p &lt; 0.01
          </text>
          <rect
            x={56}
            y={-9}
            width={16}
            height={12}
            fill="color-mix(in srgb, var(--color-penumbra-cyan) 80%, transparent)"
          />
          <text x={82} y={0} fontSize={9} fill="var(--color-penumbra-dim)">
            p &lt; 0.05
          </text>
          <rect
            x={130}
            y={-9}
            width={16}
            height={12}
            fill="color-mix(in srgb, var(--color-penumbra-cyan) 55%, transparent)"
          />
          <text x={156} y={0} fontSize={9} fill="var(--color-penumbra-dim)">
            p &lt; 0.10
          </text>
          <rect
            x={204}
            y={-9}
            width={16}
            height={12}
            fill="color-mix(in srgb, var(--color-penumbra-cyan) 30%, transparent)"
          />
          <text x={230} y={0} fontSize={9} fill="var(--color-penumbra-dim)">
            ns
          </text>
        </g>
      </svg>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[10px]">
        <Stat label="lag" value={max_lag} digits={0} />
        <Stat label="n obs" value={n_obs} digits={0} />
      </div>
    </div>
  );
}

function Stat({ label, value, digits }: { label: string; value: number; digits: number }) {
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div className="tabular-nums text-[color:var(--color-penumbra-text)]">
        {value.toFixed(digits)}
      </div>
    </div>
  );
}
