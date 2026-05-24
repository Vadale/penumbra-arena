/**
 * Phase 5 Tier 3 — synthetic-trace (GAN stub) privacy-utility curve.
 *
 * Sweeps correlation-preserve ∈ [0, 1] vs (mean L2, covariance
 * Frobenius). Higher preserve → smaller fidelity gap to the real
 * distribution; privacy membership advantage is fixed at 0 since every
 * released sample is a fresh draw from the model.
 */

import { useFetchJsonOnce } from "../hooks/useFetchJson";
import { FetchError, Stat } from "./_shared";

interface Point {
  correlation_preserve: number;
  mean_l2: number;
  cov_frobenius: number;
  privacy_membership_advantage: number;
}

interface Payload {
  available: boolean;
  algorithm?: string;
  n_real?: number;
  n_features?: number;
  curve?: Point[];
}

export function DefenseGANChart() {
  const state = useFetchJsonOnce<Payload>("/defenses/gan/demo");
  const data = state.kind === "data" ? state.value : undefined;

  if (!data?.available || !data.curve) {
    if (state.kind === "error") return <FetchError message={state.message} />;
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {state.kind === "loading" ? "computing…" : "synthetic release unavailable"}
      </div>
    );
  }

  const points = data.curve;
  const width = 560;
  const height = 160;
  const padLeft = 50;
  const padRight = 10;
  const padTop = 14;
  const padBottom = 26;
  const sx = (cp: number) => padLeft + cp * (width - padLeft - padRight);
  const covMax = Math.max(...points.map((p) => p.cov_frobenius), 1e-6);
  const meanMax = Math.max(...points.map((p) => p.mean_l2), 1e-6);
  const sy = (v: number, max: number) => padTop + (1 - v / max) * (height - padTop - padBottom);

  const pathCov = points
    .map(
      (p, i) =>
        `${i === 0 ? "M" : "L"}${sx(p.correlation_preserve)},${sy(p.cov_frobenius, covMax)}`,
    )
    .join(" ");
  const pathMean = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.correlation_preserve)},${sy(p.mean_l2, meanMax)}`)
    .join(" ");

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "Gaussian stub"} accent />
        <Stat label="n real" value={data.n_real ?? 0} digits={0} />
        <Stat label="features" value={data.n_features ?? 0} digits={0} />
        <Stat label="membership Δ" value={0} digits={2} caption="model output ⇒ chance" />
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        role="img"
        aria-label="correlation preserve vs fidelity gaps"
      >
        <line
          x1={padLeft}
          y1={padTop}
          x2={padLeft}
          y2={height - padBottom}
          stroke="var(--color-penumbra-dim)"
        />
        <line
          x1={padLeft}
          y1={height - padBottom}
          x2={width - padRight}
          y2={height - padBottom}
          stroke="var(--color-penumbra-dim)"
        />
        <path d={pathCov} stroke="var(--color-penumbra-cyan)" strokeWidth={1.5} fill="none" />
        <path
          d={pathMean}
          stroke="var(--color-penumbra-ember)"
          strokeWidth={1.2}
          fill="none"
          strokeDasharray="3 2"
        />
        {points.map((p) => (
          <g key={p.correlation_preserve}>
            <circle
              cx={sx(p.correlation_preserve)}
              cy={sy(p.cov_frobenius, covMax)}
              r={2.5}
              fill="var(--color-penumbra-cyan)"
            />
            <circle
              cx={sx(p.correlation_preserve)}
              cy={sy(p.mean_l2, meanMax)}
              r={2.5}
              fill="var(--color-penumbra-ember)"
            />
            <text
              x={sx(p.correlation_preserve)}
              y={height - padBottom + 12}
              textAnchor="middle"
              fontSize={8}
              fill="var(--color-penumbra-dim)"
            >
              cp={p.correlation_preserve.toFixed(2)}
            </text>
          </g>
        ))}
        <text x={6} y={padTop + 6} fontSize={8} fill="var(--color-penumbra-cyan)">
          cov Frobenius gap (scaled)
        </text>
        <text x={6} y={padTop + 18} fontSize={8} fill="var(--color-penumbra-ember)">
          mean L2 gap (scaled)
        </text>
      </svg>

      <div className="grid grid-cols-5 gap-1 text-[9px]">
        {points.map((p) => (
          <Stat
            key={p.correlation_preserve}
            label={`cp=${p.correlation_preserve.toFixed(2)}`}
            value={p.cov_frobenius}
            digits={3}
            caption={`μ L2 ${p.mean_l2.toFixed(3)}`}
          />
        ))}
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Stub releases a fresh draw from a Gaussian fitted to the real features. cp=0 destroys
        correlations (independent margins), cp=1 preserves the empirical covariance. Real CycleGAN /
        TimeGAN deferred — same API surface, drop-in replacement.
      </div>
    </div>
  );
}
