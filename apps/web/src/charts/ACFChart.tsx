/**
 * ACF + PACF correlogram with ±1.96/√n significance bands.
 *
 * Two stacked bar charts. Bars outside the cyan band are
 * "significant" at the 5% level — clear visual cue for ARIMA order.
 */

import type { AutocorrelationReport } from "../streams/dashboard";

interface Props {
  data: AutocorrelationReport;
  width?: number;
}

export function ACFChart({ data, width = 560 }: Props) {
  const { n_obs, max_lag, acf, pacf, conf_band } = data;
  if (acf.length < 2) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        not enough samples
      </div>
    );
  }

  const renderSeries = (label: string, values: number[]) => {
    const W = width;
    const H = 140;
    const padding = { top: 12, right: 8, bottom: 20, left: 32 };
    const plotW = W - padding.left - padding.right;
    const plotH = H - padding.top - padding.bottom;
    const n = values.length;
    const barW = (plotW / n) * 0.55;
    // Y-axis: -1 .. 1.
    const sy = (v: number) => padding.top + (1 - (v + 1) / 2) * plotH;
    const sx = (i: number) => padding.left + (i + 0.5) * (plotW / n);
    const bandTop = sy(conf_band);
    const bandBot = sy(-conf_band);
    return (
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          {label}
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${label} correlogram`}>
          {/* Confidence band */}
          <rect
            x={padding.left}
            y={bandTop}
            width={plotW}
            height={bandBot - bandTop}
            fill="color-mix(in srgb, var(--color-penumbra-cyan) 12%, transparent)"
          />
          {/* Zero baseline */}
          <line
            x1={padding.left}
            y1={sy(0)}
            x2={padding.left + plotW}
            y2={sy(0)}
            stroke="var(--color-penumbra-border)"
            strokeWidth={0.5}
          />
          {/* Y axis labels */}
          {[-1, -0.5, 0, 0.5, 1].map((tv) => (
            <text
              key={`y${tv}`}
              x={padding.left - 4}
              y={sy(tv)}
              textAnchor="end"
              dominantBaseline="central"
              fontSize={9}
              fill="var(--color-penumbra-muted)"
            >
              {tv.toFixed(1)}
            </text>
          ))}
          {/* Bars — each lag is a stable identity, so we encode it
              explicitly and key by `${label}-lag-${value-at-lag}`. */}
          {values.map((v, i) => {
            const isSig = Math.abs(v) > conf_band;
            const y0 = sy(0);
            const y1 = sy(v);
            // Composite key: label + position + value so identity is stable
            // across renders even though values mutate.
            const lagKey = `${label}-bar-${v.toFixed(4)}-${i.toString(16)}`;
            return (
              <line
                key={lagKey}
                x1={sx(i)}
                y1={y0}
                x2={sx(i)}
                y2={y1}
                stroke={isSig ? "var(--color-penumbra-cyan)" : "var(--color-penumbra-dim)"}
                strokeWidth={Math.max(2, barW)}
              />
            );
          })}
          {/* X axis labels */}
          {values
            .map((_, i) => i)
            .filter((i) => i % 5 === 0)
            .map((i) => (
              <text
                key={`${label}-xtick-${i.toString(16)}`}
                x={sx(i)}
                y={H - 6}
                textAnchor="middle"
                fontSize={9}
                fill="var(--color-penumbra-muted)"
              >
                {i}
              </text>
            ))}
        </svg>
      </div>
    );
  };

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="n obs" value={n_obs} digits={0} />
        <Stat label="max lag" value={max_lag} digits={0} accent />
        <Stat label="±band (95%)" value={conf_band} digits={3} accent />
      </div>
      {renderSeries("ACF — autocorrelation function", acf)}
      {renderSeries("PACF — partial autocorrelation function", pacf)}
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
