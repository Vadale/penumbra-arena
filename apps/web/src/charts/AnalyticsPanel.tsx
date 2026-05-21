/**
 * Streaming-analytics dashboard panel — DF-density + sparklines.
 *
 * Each cell now carries both the latest value AND its sparkline over
 * the last ~30 seconds of polls. The sparkline turns numbers into
 * shape — you can see at a glance whether a metric is climbing,
 * collapsing, or stable.
 */

import { useDashboardLive } from "../streams/dashboard";
import { PersistenceBarcode } from "./PersistenceBarcode";
import { Sparkline } from "./Sparkline";

function fmt(value: number | null, digits = 3): string {
  if (value === null || !Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1000) return value.toFixed(0);
  return value.toFixed(digits);
}

function Cell({
  label,
  value,
  caption,
  history,
  accent,
  ember,
}: {
  label: string;
  value: string;
  caption?: string;
  history?: number[];
  accent?: boolean;
  ember?: boolean;
}) {
  const valueClass = ember
    ? "text-[color:var(--color-penumbra-ember)]"
    : accent
      ? "text-[color:var(--color-penumbra-cyan)]"
      : "text-[color:var(--color-penumbra-text)]";
  const sparkColor = ember ? "var(--color-penumbra-ember)" : "var(--color-penumbra-cyan)";
  const sparkFill = ember
    ? "color-mix(in srgb, var(--color-penumbra-ember) 18%, transparent)"
    : "color-mix(in srgb, var(--color-penumbra-cyan) 18%, transparent)";
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[9px] uppercase tracking-[0.15em] text-[color:var(--color-penumbra-dim)]">
            {label}
          </div>
          <div className={`tabular-nums text-[13px] leading-tight ${valueClass}`}>{value}</div>
        </div>
        {history && history.length > 1 && (
          <Sparkline
            values={history}
            width={50}
            height={20}
            color={sparkColor}
            fillColor={sparkFill}
          />
        )}
      </div>
      {caption && (
        <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">{caption}</div>
      )}
    </div>
  );
}

export function AnalyticsPanel() {
  const { snap, history } = useDashboardLive();
  if (snap === null) {
    return (
      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
        analytics connecting<span className="animate-pulse">…</span>
      </div>
    );
  }

  const summary = snap.summary;
  const dpExhausted = snap.dp_budget !== null && snap.dp_budget.epsilon_remaining < 1.0;

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 gap-1">
        <Cell
          label="traj.mean"
          value={fmt(summary?.mean ?? null)}
          caption={summary ? `n=${summary.n}` : undefined}
          history={history.trajectory_mean}
        />
        <Cell
          label="traj.std"
          value={fmt(summary?.std ?? null)}
          caption={summary ? `iqr=${fmt(summary.iqr)}` : undefined}
          history={history.trajectory_std}
        />
        <Cell
          label="hdbscan"
          value={snap.hdbscan_n_clusters !== null ? String(snap.hdbscan_n_clusters) : "—"}
          caption={snap.hdbscan_n_noise !== null ? `noise=${snap.hdbscan_n_noise}` : undefined}
          history={history.hdbscan_clusters}
        />
        <Cell
          label="arima.next"
          value={fmt(snap.arima_next)}
          caption={snap.arima_std !== null ? `σ=${fmt(snap.arima_std)}` : undefined}
          history={history.arima_next}
        />
        <Cell
          label="sinkhorn"
          value={fmt(snap.sinkhorn_cost)}
          caption="W₁"
          history={history.sinkhorn_cost}
        />
        <Cell label="var.95" value={fmt(snap.var95)} caption="tail risk" history={history.var95} />
        <Cell
          label="h₀"
          value={fmt(snap.h0_total)}
          caption="components"
          history={history.h0_total}
        />
        <Cell label="h₁" value={fmt(snap.h1_total)} caption="loops" history={history.h1_total} />
        <Cell
          label="bayes.θ"
          value={fmt(snap.bayesian_theta)}
          caption="P(high‖)"
          history={history.bayesian_theta}
        />
        <Cell
          label="changepts"
          value={snap.changepoints.length > 0 ? snap.changepoints.join(",") : "—"}
        />
        <Cell
          label="dp.ε spent"
          value={snap.dp_budget ? fmt(snap.dp_budget.epsilon_spent, 2) : "—"}
          caption={
            snap.dp_budget
              ? `rem ${fmt(snap.dp_budget.epsilon_remaining, 2)} / ${fmt(snap.dp_budget.epsilon_total, 1)}`
              : "dp off"
          }
          history={history.dp_epsilon_spent}
          ember={dpExhausted}
          accent={!!snap.dp_budget && !dpExhausted}
        />
        <Cell
          label="sigs.ok"
          value={snap.signing_stats.verified.toLocaleString()}
          caption={
            snap.signing_stats.rejected > 0
              ? `${snap.signing_stats.rejected} bad · ${snap.signing_stats.n_agents} ag`
              : `${snap.signing_stats.n_agents} ag · 0 bad`
          }
          history={history.signing_verified}
          ember={snap.signing_stats.rejected > 0}
          accent
        />
        <Cell
          label="topics"
          value={snap.n_topics !== null ? String(snap.n_topics) : "—"}
          caption={
            snap.n_topics && snap.n_topics > 0
              ? (Object.values(snap.topic_top_words)[0]?.slice(0, 3).join("·") ?? "")
              : "warming"
          }
          history={history.n_topics}
        />
      </div>

      {summary && (
        <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 text-[10px] text-[color:var(--color-penumbra-muted)]">
          <span className="text-[color:var(--color-penumbra-dim)]">95% ci </span>
          <span className="tabular-nums text-[color:var(--color-penumbra-text)]">
            [{fmt(summary.ci95_low)}, {fmt(summary.ci95_high)}]
          </span>
        </div>
      )}

      {(snap.h0_bars.length > 0 || snap.h1_bars.length > 0) && (
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-[0.18em] text-[color:var(--color-penumbra-dim)]">
            persistence barcode
          </div>
          <PersistenceBarcode h0Bars={snap.h0_bars} h1Bars={snap.h1_bars} />
        </div>
      )}
    </div>
  );
}
