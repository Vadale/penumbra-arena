/**
 * One-way ANOVA: F-test result + per-group mean ± SE point chart.
 *
 * Headline = F, p, df. Body = per-group horizontal point-and-error
 * with the grand mean as an ember vertical line.
 */

import type { ANOVAReport } from "../streams/dashboard";
import { Stat } from "./_shared";

interface Props {
  data: ANOVAReport;
  width?: number;
}

export function ANOVAChart({ data, width = 560 }: Props) {
  const {
    f_statistic,
    p_value,
    df_between,
    df_within,
    grouping,
    group_names,
    group_means,
    group_se,
    group_n,
    grand_mean,
  } = data;
  if (group_names.length < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        ANOVA needs ≥ 2 groups with ≥ 2 obs each
      </div>
    );
  }
  const lo = Math.min(...group_means.map((m, i) => m - 1.96 * (group_se[i] ?? 0)));
  const hi = Math.max(...group_means.map((m, i) => m + 1.96 * (group_se[i] ?? 0)));
  const span = hi - lo || 1;
  const pad = span * 0.08;
  const xLo = lo - pad;
  const xHi = hi + pad;
  const sx = (v: number) => 60 + ((v - xLo) / (xHi - xLo)) * (width - 90);

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="F" value={f_statistic} digits={3} accent />
        <Stat
          label="p-value"
          value={p_value}
          digits={4}
          ember={p_value < 0.05}
          accent={p_value >= 0.05}
        />
        <Stat label="df between" value={df_between} digits={0} />
        <Stat label="df within" value={df_within} digits={0} />
      </div>

      <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">grouping: {grouping}</div>

      <svg
        viewBox={`0 0 ${width} ${group_names.length * 28 + 24}`}
        width="100%"
        role="img"
        aria-label="ANOVA group means + 95% CIs"
      >
        {/* Grand mean line */}
        <line
          x1={sx(grand_mean)}
          y1={0}
          x2={sx(grand_mean)}
          y2={group_names.length * 28 + 8}
          stroke="var(--color-penumbra-ember)"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
        <text x={sx(grand_mean) + 4} y={10} fontSize={9} fill="var(--color-penumbra-ember)">
          grand mean = {grand_mean.toFixed(3)}
        </text>
        {/* Per-group point + 95% CI */}
        {group_names.map((name, i) => {
          const y = 16 + i * 28;
          const m = group_means[i] ?? 0;
          const se = group_se[i] ?? 0;
          const n = group_n[i] ?? 0;
          const ciLo = sx(m - 1.96 * se);
          const ciHi = sx(m + 1.96 * se);
          return (
            <g key={name}>
              <text x={6} y={y + 6} fontSize={10} fill="var(--color-penumbra-muted)">
                {name}
              </text>
              <line
                x1={ciLo}
                y1={y + 6}
                x2={ciHi}
                y2={y + 6}
                stroke="var(--color-penumbra-cyan)"
                strokeWidth={1.4}
              />
              <line
                x1={ciLo}
                y1={y + 2}
                x2={ciLo}
                y2={y + 10}
                stroke="var(--color-penumbra-cyan)"
                strokeWidth={1.4}
              />
              <line
                x1={ciHi}
                y1={y + 2}
                x2={ciHi}
                y2={y + 10}
                stroke="var(--color-penumbra-cyan)"
                strokeWidth={1.4}
              />
              <circle cx={sx(m)} cy={y + 6} r={3.5} fill="var(--color-penumbra-cyan)" />
              <text
                x={width - 6}
                y={y + 6}
                textAnchor="end"
                dominantBaseline="central"
                fontSize={9}
                fill="var(--color-penumbra-dim)"
              >
                n={n} · μ={m.toFixed(3)} · se={se.toFixed(3)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
