/**
 * Laplacian spectrum + Fiedler vector visualisation.
 *
 * Top panel: bar chart of the bottom 4-5 eigenvalues, with the
 * Fiedler value λ₂ highlighted.
 * Bottom panel: the Fiedler vector — one bar per node, color-split
 * by sign so the optimal-cut partition reads at a glance.
 */

import type { SpectralReport } from "../streams/dashboard";

interface Props {
  data: SpectralReport;
  width?: number;
  height?: number;
}

export function SpectralChart({ data, width = 560 }: Props) {
  const { eigenvalues, fiedler_value, n_nodes, n_edges, fiedler_vector } = data;

  if (eigenvalues.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        spectral warming up
      </div>
    );
  }

  const maxEig = Math.max(...eigenvalues);
  const k = eigenvalues.length;
  const fvAbs = Math.max(...fiedler_vector.map((v) => Math.abs(v)), 1e-9);

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="fiedler λ₂" value={fiedler_value} digits={4} accent />
        <Stat label="nodes" value={n_nodes} digits={0} />
        <Stat label="edges" value={n_edges} digits={0} />
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          bottom eigenvalues (excluding λ₁ = 0)
        </div>
        <svg
          viewBox={`0 0 ${width} 160`}
          width="100%"
          role="img"
          aria-label="Laplacian eigenvalue bars"
        >
          {eigenvalues.map((v, i) => {
            const barW = (width - 80) / k;
            const x = 50 + i * barW;
            const h = maxEig > 0 ? (v / maxEig) * 120 : 0;
            const isFiedler = i === 0;
            return (
              // Eigenvalues are sorted ASC and unique enough to be a stable key.
              <g key={`eig-${v.toFixed(6)}`}>
                <rect
                  x={x + 2}
                  y={140 - h}
                  width={barW - 6}
                  height={h}
                  fill={
                    isFiedler
                      ? "color-mix(in srgb, var(--color-penumbra-ember) 35%, transparent)"
                      : "color-mix(in srgb, var(--color-penumbra-cyan) 28%, transparent)"
                  }
                  stroke={isFiedler ? "var(--color-penumbra-ember)" : "var(--color-penumbra-cyan)"}
                  strokeWidth={1}
                />
                <text
                  x={x + (barW - 6) / 2 + 2}
                  y={154}
                  textAnchor="middle"
                  fontSize={9}
                  fill="var(--color-penumbra-muted)"
                >
                  λ{i + 2}
                </text>
                <text
                  x={x + (barW - 6) / 2 + 2}
                  y={136 - h}
                  textAnchor="middle"
                  fontSize={9}
                  fill="var(--color-penumbra-text)"
                >
                  {v.toFixed(3)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          Fiedler vector (sign = min-cut partition)
        </div>
        <svg viewBox={`0 0 ${width} 130`} width="100%" role="img" aria-label="Fiedler vector bars">
          {fiedler_vector.map((v, i) => {
            const barW = (width - 16) / fiedler_vector.length;
            const x = 8 + i * barW;
            const h = (Math.abs(v) / fvAbs) * 55;
            const y = v >= 0 ? 65 - h : 65;
            const k = `fv-${i}-${fiedler_vector.length}`;
            return (
              <rect
                key={k}
                x={x + 0.5}
                y={y}
                width={Math.max(1, barW - 1)}
                height={h}
                fill={v >= 0 ? "var(--color-penumbra-cyan)" : "var(--color-penumbra-ember)"}
                opacity={0.75}
              />
            );
          })}
          <line
            x1={8}
            y1={65}
            x2={width - 8}
            y2={65}
            stroke="var(--color-penumbra-border)"
            strokeWidth={0.5}
          />
          <text x={10} y={125} fontSize={9} fill="var(--color-penumbra-dim)">
            cyan = partition A · ember = partition B
          </text>
        </svg>
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
