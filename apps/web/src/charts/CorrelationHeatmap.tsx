/**
 * Pearson + Spearman correlation heatmap.
 *
 * Two K×K matrices side by side: each cell colored by correlation,
 * value printed inside. Pearson on the left (linear assoc), Spearman
 * on the right (monotone assoc).
 */

import type { CorrelationMatrix } from "../streams/dashboard";
import { Stat } from "./_shared";

interface Props {
  data: CorrelationMatrix;
  width?: number;
}

function cellColor(r: number, isDiag: boolean): string {
  if (isDiag) return "color-mix(in srgb, var(--color-penumbra-dim) 60%, transparent)";
  if (!Number.isFinite(r)) return "rgba(40, 45, 55, 0.4)";
  if (r > 0) {
    const intensity = Math.min(0.85, Math.abs(r));
    return `color-mix(in srgb, var(--color-penumbra-cyan) ${Math.round(intensity * 80)}%, transparent)`;
  }
  const intensity = Math.min(0.85, Math.abs(r));
  return `color-mix(in srgb, var(--color-penumbra-ember) ${Math.round(intensity * 80)}%, transparent)`;
}

export function CorrelationHeatmap({ data, width = 560 }: Props) {
  const { series_names, pearson, spearman, n_obs } = data;
  const K = series_names.length;
  if (K < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        not enough series
      </div>
    );
  }

  const cell = Math.min(60, (width - 130) / (K * 2));
  const matrixW = K * cell;
  const totalH = K * cell + 70;

  const drawMatrix = (matrix: number[][], xOffset: number, title: string) => (
    <g transform={`translate(${xOffset}, 24)`}>
      <text
        x={matrixW / 2}
        y={-8}
        textAnchor="middle"
        fontSize={10}
        fill="var(--color-penumbra-muted)"
      >
        {title}
      </text>
      {/* Column labels */}
      {series_names.map((name, j) => (
        <text
          key={`${title}-col-${name}`}
          x={(j + 0.5) * cell}
          y={-2}
          textAnchor="middle"
          fontSize={9}
          fill="var(--color-penumbra-dim)"
        >
          {name}
        </text>
      ))}
      {/* Row labels — only for the first matrix to save space */}
      {xOffset < 70 &&
        series_names.map((name, i) => (
          <text
            key={`row-${name}`}
            x={-4}
            y={(i + 0.5) * cell + 4}
            textAnchor="end"
            fontSize={9}
            fill="var(--color-penumbra-muted)"
          >
            {name}
          </text>
        ))}
      {/* Cells */}
      {matrix.map((row, i) =>
        row.map((r, j) => {
          const isDiag = i === j;
          return (
            <g key={`${title}-${series_names[i]}-${series_names[j]}`}>
              <rect
                x={j * cell}
                y={i * cell}
                width={cell - 1}
                height={cell - 1}
                fill={cellColor(r, isDiag)}
                stroke="var(--color-penumbra-bg)"
                strokeWidth={0.5}
              />
              {!isDiag && (
                <text
                  x={(j + 0.5) * cell}
                  y={(i + 0.5) * cell + 4}
                  textAnchor="middle"
                  fontSize={Math.min(11, cell * 0.32)}
                  fill="var(--color-penumbra-text)"
                  fontWeight={Math.abs(r) > 0.7 ? 600 : 400}
                >
                  {r.toFixed(2)}
                </text>
              )}
            </g>
          );
        }),
      )}
    </g>
  );

  return (
    <div className="font-mono">
      <svg
        viewBox={`0 0 ${width} ${totalH}`}
        width="100%"
        role="img"
        aria-label="Pearson + Spearman correlation heatmaps"
      >
        {drawMatrix(pearson, 60, "Pearson r")}
        {drawMatrix(spearman, 60 + matrixW + 30, "Spearman ρ")}
      </svg>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[10px]">
        <Stat label="n obs" value={n_obs} digits={0} accent />
        <Stat label="series" value={K} digits={0} />
      </div>
      <div className="mt-1 text-[9px] text-[color:var(--color-penumbra-dim)]">
        cyan = positive · ember = negative · intensity = |r|
      </div>
    </div>
  );
}
