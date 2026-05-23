/**
 * Live histogram of actions chosen by the policy at the current tick.
 */

import type { ActionHistogram } from "../streams/learning";
import { Stat } from "./_shared";

interface Props {
  data: ActionHistogram;
  width?: number;
}

export function ActionHistogramChart({ data, width = 560 }: Props) {
  const { histogram, n_agents, temperature, enabled } = data;
  if (!histogram || histogram.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        action histogram warming up
      </div>
    );
  }
  const maxCount = Math.max(...histogram.map((r) => r.count), 1);
  const total = histogram.reduce((s, r) => s + r.count, 0);
  const barH = 22;

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="agents" value={n_agents ?? total} digits={0} accent />
        <Stat label="temperature" value={temperature ?? 1.0} digits={2} />
        <Stat label="policy" value={enabled ? "MAPPO" : "RANDOM"} />
      </div>
      <svg
        viewBox={`0 0 ${width} ${histogram.length * (barH + 4) + 6}`}
        width="100%"
        role="img"
        aria-label="action histogram"
      >
        {histogram.map((row, i) => {
          const y = i * (barH + 4) + 4;
          const w = (row.count / maxCount) * (width - 200);
          const isRandom = row.action === "random";
          const isStay = row.action === "stay";
          const color = isRandom
            ? "var(--color-penumbra-ember)"
            : isStay
              ? "color-mix(in srgb, var(--color-penumbra-dim) 60%, transparent)"
              : "var(--color-penumbra-cyan)";
          return (
            <g key={row.action}>
              <text
                x={6}
                y={y + barH / 2}
                fontSize={10}
                dominantBaseline="central"
                fill="var(--color-penumbra-muted)"
              >
                {row.action}
              </text>
              <rect
                x={100}
                y={y}
                width={Math.max(2, w)}
                height={barH}
                fill={color}
                opacity={0.65}
                stroke={color}
                strokeWidth={0.7}
              />
              <text
                x={104 + Math.max(2, w)}
                y={y + barH / 2}
                fontSize={10}
                dominantBaseline="central"
                fill="var(--color-penumbra-text)"
              >
                {row.count}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
