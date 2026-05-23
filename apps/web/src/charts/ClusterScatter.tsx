/**
 * 2-D scatter of agents projected onto PC1/PC2, colored by HDBSCAN label.
 *
 * Renders the backend's ClusterScatter: each point is an agent at
 * (x, y) = (its PC1 score, its PC2 score), color-coded by faction.
 * Label -1 (noise) renders grey; positive labels get a distinct hue.
 */

import type { ClusterScatter as ClusterScatterData } from "../streams/dashboard";
import { Stat } from "./_shared";

interface Props {
  data: ClusterScatterData;
  width?: number;
  height?: number;
}

const M = { top: 14, right: 16, bottom: 26, left: 40 };

function clusterColor(label: number): string {
  if (label < 0) return "color-mix(in srgb, var(--color-penumbra-dim) 70%, transparent)";
  // Golden ratio hue spread for visually distinct factions.
  const hue = ((label * 0.6180339887) % 1) * 360;
  return `oklch(0.74 0.18 ${hue.toFixed(1)})`;
}

export function ClusterScatter({ data, width = 560, height = 360 }: Props) {
  const { points, n_clusters, n_noise } = data;
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
  const xPad = (xMax - xMin || 1) * 0.08;
  const yPad = (yMax - yMin || 1) * 0.08;

  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  const sx = (x: number) => M.left + ((x - (xMin - xPad)) / (xMax - xMin + 2 * xPad)) * plotW;
  const sy = (y: number) => M.top + (1 - (y - (yMin - yPad)) / (yMax - yMin + 2 * yPad)) * plotH;

  // Gridlines: 5 per axis.
  const xTicks = Array.from(
    { length: 5 },
    (_, i) => xMin - xPad + (i / 4) * (xMax - xMin + 2 * xPad),
  );
  const yTicks = Array.from(
    { length: 5 },
    (_, i) => yMin - yPad + (i / 4) * (yMax - yMin + 2 * yPad),
  );

  // Count agents per cluster for the legend.
  const labelCount = new Map<number, number>();
  for (const [, , l] of points) labelCount.set(l, (labelCount.get(l) ?? 0) + 1);

  return (
    <div className="font-mono">
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="cluster scatter">
        {xTicks.map((tv) => {
          const x = sx(tv);
          return (
            <line
              key={`x${tv.toFixed(3)}`}
              x1={x}
              y1={M.top}
              x2={x}
              y2={M.top + plotH}
              stroke="var(--color-penumbra-border)"
              strokeWidth={0.35}
              strokeDasharray="2 3"
            />
          );
        })}
        {yTicks.map((tv) => {
          const y = sy(tv);
          return (
            <line
              key={`y${tv.toFixed(3)}`}
              x1={M.left}
              y1={y}
              x2={M.left + plotW}
              y2={y}
              stroke="var(--color-penumbra-border)"
              strokeWidth={0.35}
              strokeDasharray="2 3"
            />
          );
        })}
        <text x={M.left} y={height - 8} fontSize={9} fill="var(--color-penumbra-muted)">
          PC1
        </text>
        <text
          x={M.left - 26}
          y={M.top + plotH / 2}
          fontSize={9}
          fill="var(--color-penumbra-muted)"
          transform={`rotate(-90, ${M.left - 26}, ${M.top + plotH / 2})`}
        >
          PC2
        </text>
        {points.map(([x, y, l]) => (
          <circle
            key={`${x.toFixed(4)}-${y.toFixed(4)}-${l}`}
            cx={sx(x)}
            cy={sy(y)}
            r={3.4}
            fill={clusterColor(l)}
            stroke="var(--color-penumbra-bg)"
            strokeWidth={0.6}
          />
        ))}
      </svg>
      <div className="mt-2 grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="clusters" value={n_clusters} accent />
        <Stat label="noise" value={n_noise} ember={n_noise > points.length / 3} />
        <Stat label="agents" value={points.length} />
      </div>
      <div className="mt-1 flex flex-wrap gap-1 text-[9px]">
        {[...labelCount.entries()]
          .sort((a, b) => a[0] - b[0])
          .map(([label, count]) => (
            <span
              key={label}
              className="border border-[color:var(--color-penumbra-border)] px-1 py-0.5"
              style={{ color: clusterColor(label) }}
            >
              {label === -1 ? "noise" : `c${label}`}
              <span className="ml-1 text-[color:var(--color-penumbra-dim)]">{count}</span>
            </span>
          ))}
      </div>
    </div>
  );
}
