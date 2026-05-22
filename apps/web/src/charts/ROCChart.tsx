/**
 * ROC curve + AUC for the logit classifier.
 */

import type { ROCData } from "../streams/dashboard";

interface Props {
  data: ROCData;
  width?: number;
  height?: number;
}

const M = { top: 14, right: 16, bottom: 30, left: 50 };

export function ROCChart({ data, width = 480, height = 360 }: Props) {
  const { fpr, tpr, auc } = data;
  if (fpr.length < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        ROC warming up
      </div>
    );
  }

  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  const sx = (x: number) => M.left + x * plotW;
  const sy = (y: number) => M.top + (1 - y) * plotH;

  const curvePts = fpr.map((x, i) => `${sx(x)},${sy(tpr[i] ?? 0)}`).join(" ");
  const ticks = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="font-mono">
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="ROC curve">
        {ticks.map((tv) => (
          <g key={`g${tv}`}>
            <line
              x1={M.left}
              y1={sy(tv)}
              x2={M.left + plotW}
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
            <text
              x={sx(tv)}
              y={M.top + plotH + 14}
              textAnchor="middle"
              fontSize={9}
              fill="var(--color-penumbra-muted)"
            >
              {tv.toFixed(2)}
            </text>
          </g>
        ))}
        {/* Random reference line */}
        <line
          x1={sx(0)}
          y1={sy(0)}
          x2={sx(1)}
          y2={sy(1)}
          stroke="var(--color-penumbra-ember)"
          strokeWidth={0.9}
          strokeDasharray="3 3"
        />
        {/* AUC fill */}
        <polygon
          points={`${sx(0)},${sy(0)} ${curvePts} ${sx(1)},${sy(0)}`}
          fill="color-mix(in srgb, var(--color-penumbra-cyan) 14%, transparent)"
        />
        {/* ROC curve */}
        <polyline
          points={curvePts}
          fill="none"
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={1.7}
        />
        <text
          x={width / 2}
          y={height - 8}
          textAnchor="middle"
          fontSize={10}
          fill="var(--color-penumbra-muted)"
        >
          false positive rate
        </text>
        <text
          x={M.left - 32}
          y={M.top + plotH / 2}
          fontSize={10}
          fill="var(--color-penumbra-muted)"
          transform={`rotate(-90, ${M.left - 32}, ${M.top + plotH / 2})`}
        >
          true positive rate
        </text>
      </svg>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[10px]">
        <Stat label="AUC" value={auc} digits={3} accent={auc >= 0.7} ember={auc < 0.55} />
        <Stat label="points" value={fpr.length} digits={0} />
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  digits,
  accent,
  ember,
}: {
  label: string;
  value: number;
  digits: number;
  accent?: boolean;
  ember?: boolean;
}) {
  const cls = ember
    ? "text-[color:var(--color-penumbra-ember)]"
    : accent
      ? "text-[color:var(--color-penumbra-cyan)]"
      : "text-[color:var(--color-penumbra-text)]";
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div className={`tabular-nums ${cls}`}>{value.toFixed(digits)}</div>
    </div>
  );
}
