/**
 * IPW vs AIPW ATE estimates + propensity-score overlap histograms.
 *
 * Compares the two estimators side by side with their SEs, and
 * shows the propensity-score distributions per group so the user
 * sees the positivity / overlap assumption visually.
 */

import type { CausalEstimate } from "../streams/dashboard";

interface Props {
  data: CausalEstimate;
  width?: number;
}

function histogram(values: number[], bins: number): { x: number; count: number }[] {
  if (values.length === 0) return [];
  const out: { x: number; count: number }[] = [];
  const step = 1.0 / bins;
  for (let i = 0; i < bins; i++) {
    const lo = i * step;
    const hi = lo + step;
    const c = values.filter((v) => v >= lo && v < hi).length;
    out.push({ x: lo + step / 2, count: c });
  }
  return out;
}

export function CausalChart({ data, width = 560 }: Props) {
  const {
    n_treated,
    n_control,
    ipw_ate,
    ipw_se,
    aipw_ate,
    aipw_se,
    propensity_treated,
    propensity_control,
  } = data;

  const bins = 20;
  const hT = histogram(propensity_treated, bins);
  const hC = histogram(propensity_control, bins);
  const hMax = Math.max(...hT.map((b) => b.count), ...hC.map((b) => b.count), 1);
  const barW = (width - 32) / bins;

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="treated" value={n_treated} digits={0} accent />
        <Stat label="control" value={n_control} digits={0} />
        <Stat
          label="IPW ATE"
          value={ipw_ate}
          digits={3}
          accent
          caption={`SE ${ipw_se.toFixed(3)}`}
        />
        <Stat
          label="AIPW ATE"
          value={aipw_ate}
          digits={3}
          accent
          caption={`SE ${aipw_se.toFixed(3)}`}
        />
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          propensity overlap (top = treated · bottom = control)
        </div>
        <svg
          viewBox={`0 0 ${width} 170`}
          width="100%"
          role="img"
          aria-label="propensity histograms"
        >
          {/* Treated histogram on top */}
          {hT.map((b) => {
            const x = 16 + Math.floor(b.x * bins) * barW;
            const h = (b.count / hMax) * 65;
            return (
              <rect
                key={`t${b.x.toFixed(3)}`}
                x={x + 0.5}
                y={75 - h}
                width={barW - 1}
                height={h}
                fill="var(--color-penumbra-cyan)"
                opacity={0.55}
              />
            );
          })}
          {/* Control histogram on bottom */}
          {hC.map((b) => {
            const x = 16 + Math.floor(b.x * bins) * barW;
            const h = (b.count / hMax) * 65;
            return (
              <rect
                key={`c${b.x.toFixed(3)}`}
                x={x + 0.5}
                y={85}
                width={barW - 1}
                height={h}
                fill="var(--color-penumbra-ember)"
                opacity={0.55}
              />
            );
          })}
          {/* baseline */}
          <line
            x1={16}
            y1={80}
            x2={width - 16}
            y2={80}
            stroke="var(--color-penumbra-border)"
            strokeWidth={0.5}
          />
          {/* X-axis ticks */}
          {[0, 0.25, 0.5, 0.75, 1].map((t) => {
            const x = 16 + t * (width - 32);
            return (
              <g key={`tk${t}`}>
                <line
                  x1={x}
                  y1={155}
                  x2={x}
                  y2={160}
                  stroke="var(--color-penumbra-border)"
                  strokeWidth={0.5}
                />
                <text
                  x={x}
                  y={167}
                  textAnchor="middle"
                  fontSize={9}
                  fill="var(--color-penumbra-muted)"
                >
                  {t.toFixed(2)}
                </text>
              </g>
            );
          })}
          <text
            x={width / 2}
            y={148}
            textAnchor="middle"
            fontSize={9}
            fill="var(--color-penumbra-muted)"
          >
            propensity P(treated | x)
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
  caption,
}: {
  label: string;
  value: number;
  digits: number;
  accent?: boolean;
  caption?: string;
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
      {caption ? (
        <div className="text-[8px] text-[color:var(--color-penumbra-dim)]">{caption}</div>
      ) : null}
    </div>
  );
}
