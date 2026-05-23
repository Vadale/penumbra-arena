/**
 * Permutation-test histogram of the null distribution + observed marker.
 */

import type { PermutationReport } from "../streams/dashboard";
import { Stat } from "./_shared";

interface Props {
  data: PermutationReport;
  width?: number;
  height?: number;
}

const M = { top: 14, right: 16, bottom: 26, left: 40 };

export function PermutationChart({ data, width = 560, height = 320 }: Props) {
  const { observed_ate, null_samples, p_two_sided, n_permutations } = data;
  if (null_samples.length < 5) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        permutation warming up
      </div>
    );
  }

  const bins = 30;
  const xMin = Math.min(...null_samples, observed_ate);
  const xMax = Math.max(...null_samples, observed_ate);
  const step = (xMax - xMin) / bins || 1;
  const counts = new Array(bins).fill(0);
  for (const v of null_samples) {
    const bucket = Math.min(bins - 1, Math.max(0, Math.floor((v - xMin) / step)));
    counts[bucket]++;
  }
  const maxC = Math.max(...counts, 1);

  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  const sx = (v: number) => M.left + ((v - xMin) / (xMax - xMin || 1)) * plotW;
  const sy = (c: number) => M.top + (1 - c / maxC) * plotH;
  const barW = plotW / bins - 1;

  const xTicks = Array.from({ length: 5 }, (_, i) => xMin + (i / 4) * (xMax - xMin));

  return (
    <div className="font-mono">
      <svg
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="permutation null distribution"
      >
        {/* Histogram bars */}
        {counts.map((c, i) => {
          const x0 = M.left + (i / bins) * plotW;
          const barX = xMin + (i + 0.5) * step;
          // Tail beyond observed gets ember; rest cyan.
          const isTail = Math.abs(barX) >= Math.abs(observed_ate);
          return (
            <rect
              key={`bin-${barX.toFixed(4)}`}
              x={x0 + 0.5}
              y={sy(c)}
              width={barW}
              height={Math.max(0, plotH - (sy(c) - M.top))}
              fill={isTail ? "var(--color-penumbra-ember)" : "var(--color-penumbra-cyan)"}
              opacity={0.55}
            />
          );
        })}
        {/* Observed ATE marker */}
        <line
          x1={sx(observed_ate)}
          y1={M.top}
          x2={sx(observed_ate)}
          y2={M.top + plotH}
          stroke="var(--color-penumbra-text)"
          strokeWidth={1.4}
        />
        <text
          x={sx(observed_ate)}
          y={M.top - 4}
          textAnchor="middle"
          fontSize={10}
          fill="var(--color-penumbra-text)"
        >
          observed = {observed_ate.toFixed(3)}
        </text>
        {xTicks.map((tv) => (
          <text
            key={`x${tv.toFixed(3)}`}
            x={sx(tv)}
            y={height - M.bottom + 14}
            textAnchor="middle"
            fontSize={9}
            fill="var(--color-penumbra-muted)"
          >
            {tv.toFixed(2)}
          </text>
        ))}
      </svg>

      <div className="mt-2 grid grid-cols-3 gap-2 text-[10px]">
        <Stat
          label="p (two-sided)"
          value={p_two_sided}
          digits={4}
          ember={p_two_sided < 0.05}
          accent={p_two_sided >= 0.05}
        />
        <Stat label="observed ATE" value={observed_ate} digits={3} />
        <Stat label="permutations" value={n_permutations} digits={0} />
      </div>
    </div>
  );
}
