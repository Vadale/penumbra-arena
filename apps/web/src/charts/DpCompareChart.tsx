/**
 * DP comparison — clean vs noised heatmap side by side.
 *
 * Polls /dp/compare and renders two bar charts (one per node-density
 * vector) so the user can SEE the Laplace noise added on top of the
 * clean aggregate. The δ panel shows per-node residual = noised - clean.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface DPComparison {
  ready: boolean;
  clean?: number[];
  noised?: number[];
  epsilon_spent?: number;
  dp_applied?: boolean;
  tick?: number;
}

interface Props {
  width?: number;
}

const M = { top: 14, right: 12, bottom: 22, left: 36 };

export function DpCompareChart({ width = 560 }: Props) {
  const [data, setData] = useState<DPComparison | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch("/dp/compare");
        if (!res.ok) return;
        const payload = (await res.json()) as DPComparison;
        if (!cancelled) setData(payload);
      } catch {
        // ignore
      }
    };
    void poll();
    const t = window.setInterval(poll, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  if (!data?.ready || !data.clean || !data.noised) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        DP comparison warming up
      </div>
    );
  }
  const clean = data.clean;
  const noised = data.noised;
  const residual = clean.map((c, i) => (noised[i] ?? 0) - c);
  const yMax = Math.max(...clean, ...noised, 1);
  const resMax = Math.max(...residual.map((v) => Math.abs(v)), 0.5);

  const plotH = 120;
  const padded = (label: string, values: number[], color: string, ymax: number) => {
    const barW = (width - M.left - M.right) / values.length - 1;
    return (
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          {label}
        </div>
        <svg
          viewBox={`0 0 ${width} ${plotH + M.top + M.bottom}`}
          width="100%"
          role="img"
          aria-label={label}
        >
          <line
            x1={M.left}
            y1={M.top + plotH}
            x2={width - M.right}
            y2={M.top + plotH}
            stroke="var(--color-penumbra-border)"
            strokeWidth={0.4}
          />
          {values.map((v, i) => {
            const x = M.left + i * ((width - M.left - M.right) / values.length);
            const h = (Math.abs(v) / ymax) * plotH;
            const baseline = M.top + plotH;
            const y = v >= 0 ? baseline - h : baseline;
            return (
              <rect
                key={`${label}-${i}-${v.toFixed(3)}`}
                x={x + 0.5}
                y={y}
                width={Math.max(1, barW)}
                height={h}
                fill={color}
                opacity={0.75}
              />
            );
          })}
        </svg>
      </div>
    );
  };

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat
          label="DP applied"
          value={data.dp_applied ? "yes" : "no"}
          accent={!!data.dp_applied}
          ember={!data.dp_applied}
        />
        <Stat label="ε spent" value={(data.epsilon_spent ?? 0).toFixed(2)} accent />
        <Stat label="tick" value={String(data.tick ?? 0)} />
        <Stat label="nodes" value={String(clean.length)} />
      </div>
      {padded("CLEAN density (pre-DP)", clean, "var(--color-penumbra-cyan)", yMax)}
      {padded("RELEASED density (post-DP noise)", noised, "var(--color-penumbra-ember)", yMax)}
      {padded(
        "δ = noised − clean (the Laplace noise injected)",
        residual,
        "color-mix(in srgb, var(--color-penumbra-ember) 70%, white 20%)",
        resMax,
      )}
      <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
        L1 noise = {residual.reduce((s, v) => s + Math.abs(v), 0).toFixed(2)} · L2 ={" "}
        {Math.sqrt(residual.reduce((s, v) => s + v * v, 0)).toFixed(2)}
      </div>
    </div>
  );
}
