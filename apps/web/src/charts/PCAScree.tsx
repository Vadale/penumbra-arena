/**
 * PCA scree-plot + cumulative explained variance.
 *
 * Top-K eigenvalues as bars; overlaid cyan polyline showing cumulative
 * explained-variance ratio (right Y axis, 0..1). Indices: count of
 * components ≥ 1.0 eigenvalue (Kaiser rule) and components needed for
 * 90% cumulative variance.
 */

import type { PCAResult } from "../streams/dashboard";
import { Stat } from "./_shared";

interface Props {
  pca: PCAResult;
  width?: number;
  height?: number;
}

const M = { top: 14, right: 50, bottom: 30, left: 50 };

export function PCAScree({ pca, width = 560, height = 320 }: Props) {
  const { eigenvalues, explained_variance_ratio } = pca;
  if (eigenvalues.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        PCA warming up
      </div>
    );
  }

  const plotW = width - M.left - M.right;
  const plotH = height - M.top - M.bottom;
  const maxEig = Math.max(...eigenvalues);
  const k = eigenvalues.length;
  const barW = plotW / (k * 1.4);

  // Kaiser & 90% indices.
  const nKaiser = eigenvalues.filter((e) => e >= 1.0).length;
  const n90 =
    explained_variance_ratio.findIndex((c) => c >= 0.9) === -1
      ? k
      : explained_variance_ratio.findIndex((c) => c >= 0.9) + 1;

  const yEig = (v: number) => M.top + (1 - v / (maxEig || 1)) * plotH;
  const yCum = (v: number) => M.top + (1 - v) * plotH;
  const xBar = (i: number) => M.left + (i + 0.5) * (plotW / k) - barW / 2;

  // Polyline points for cumulative explained variance.
  const cumPts = explained_variance_ratio
    .map((c, i) => `${M.left + (i + 0.5) * (plotW / k)},${yCum(c)}`)
    .join(" ");

  // Y-left ticks (eigenvalues).
  const eigTicks = Array.from({ length: 5 }, (_, i) => (i / 4) * maxEig);
  // Y-right ticks (cumulative ratio).
  const cumTicks = [0, 0.25, 0.5, 0.75, 1.0];

  return (
    <div className="font-mono">
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="PCA scree plot">
        {eigTicks.map((tv) => {
          const y = yEig(tv);
          return (
            <g key={`y${tv.toFixed(3)}`}>
              <line
                x1={M.left}
                y1={y}
                x2={width - M.right}
                y2={y}
                stroke="var(--color-penumbra-border)"
                strokeWidth={0.35}
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
                {tv.toFixed(maxEig >= 10 ? 0 : 2)}
              </text>
            </g>
          );
        })}
        {/* Right axis: cumulative ratio. */}
        {cumTicks.map((tv) => (
          <text
            key={`c${tv}`}
            x={width - M.right + 4}
            y={yCum(tv)}
            dominantBaseline="central"
            fontSize={9}
            fill="color-mix(in srgb, var(--color-penumbra-cyan) 70%, white 10%)"
          >
            {(tv * 100).toFixed(0)}%
          </text>
        ))}

        {/* Eigenvalue bars. */}
        {eigenvalues.map((v, i) => {
          const pc = `pc${i + 1}`;
          return (
            <rect
              key={`bar-${pc}`}
              x={xBar(i)}
              y={yEig(v)}
              width={barW}
              height={plotH - (yEig(v) - M.top)}
              fill="color-mix(in srgb, var(--color-penumbra-cyan) 26%, transparent)"
              stroke="var(--color-penumbra-cyan)"
              strokeWidth={0.8}
            />
          );
        })}
        {/* Kaiser rule line at eigenvalue = 1. */}
        {maxEig >= 1 && (
          <line
            x1={M.left}
            y1={yEig(1)}
            x2={width - M.right}
            y2={yEig(1)}
            stroke="var(--color-penumbra-ember)"
            strokeWidth={0.8}
            strokeDasharray="3 3"
          />
        )}

        {/* Cumulative variance line. */}
        <polyline
          points={cumPts}
          fill="none"
          stroke="var(--color-penumbra-text)"
          strokeWidth={1.5}
        />
        {explained_variance_ratio.map((c, i) => {
          const pc = `pc${i + 1}`;
          return (
            <circle
              key={`dot-${pc}`}
              cx={M.left + (i + 0.5) * (plotW / k)}
              cy={yCum(c)}
              r={2.5}
              fill="var(--color-penumbra-text)"
            />
          );
        })}

        {/* x labels */}
        {eigenvalues.map((_, i) => {
          const pc = `pc${i + 1}`;
          return (
            <text
              key={`label-${pc}`}
              x={M.left + (i + 0.5) * (plotW / k)}
              y={M.top + plotH + 14}
              textAnchor="middle"
              fontSize={9}
              fill="var(--color-penumbra-muted)"
            >
              PC{i + 1}
            </text>
          );
        })}
      </svg>

      <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="λ₁" value={eigenvalues[0] ?? 0} digits={3} accent />
        <Stat label="kaiser" value={nKaiser} digits={0} />
        <Stat label="90% var" value={n90} digits={0} accent />
        <Stat
          label="cum var"
          value={(explained_variance_ratio[explained_variance_ratio.length - 1] ?? 0) * 100}
          digits={1}
          suffix="%"
        />
      </div>
    </div>
  );
}
