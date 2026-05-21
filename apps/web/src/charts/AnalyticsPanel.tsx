/**
 * Streaming-analytics dashboard panel.
 *
 * Renders the most recent DashboardSnapshot as a compact grid of
 * "metric tiles". Each tile shows one consumer's latest value plus a
 * dimmer caption — null values render as "—".
 */

import { useDashboardSnapshot } from "../streams/dashboard";
import { PersistenceBarcode } from "./PersistenceBarcode";

function fmt(value: number | null, digits = 3): string {
  if (value === null || !Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1000) return value.toFixed(0);
  return value.toFixed(digits);
}

function Tile({ label, value, caption }: { label: string; value: string; caption?: string }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-900/40 p-2">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="font-mono text-sm text-slate-100">{value}</div>
      {caption && <div className="text-[10px] text-slate-500">{caption}</div>}
    </div>
  );
}

export function AnalyticsPanel() {
  const snap = useDashboardSnapshot();
  if (snap === null) {
    return (
      <div className="text-xs text-slate-500">
        analytics connecting<span className="animate-pulse">…</span>
      </div>
    );
  }

  const summary = snap.summary;

  return (
    <div className="space-y-2">
      <div className="text-xs text-slate-500">tick {snap.tick}</div>

      <div className="grid grid-cols-2 gap-2">
        <Tile
          label="trajectory mean"
          value={fmt(summary?.mean ?? null)}
          caption={summary ? `n=${summary.n}` : undefined}
        />
        <Tile
          label="trajectory std"
          value={fmt(summary?.std ?? null)}
          caption={summary ? `IQR=${fmt(summary.iqr)}` : undefined}
        />
        <Tile
          label="HDBSCAN clusters"
          value={snap.hdbscan_n_clusters !== null ? String(snap.hdbscan_n_clusters) : "—"}
          caption={snap.hdbscan_n_noise !== null ? `noise=${snap.hdbscan_n_noise}` : undefined}
        />
        <Tile
          label="ARIMA next"
          value={fmt(snap.arima_next)}
          caption={snap.arima_std !== null ? `σ=${fmt(snap.arima_std)}` : undefined}
        />
        <Tile label="Sinkhorn cost" value={fmt(snap.sinkhorn_cost)} caption="W₁ between heatmaps" />
        <Tile label="VaR 95%" value={fmt(snap.var95)} caption="trajectory tail" />
        <Tile label="H₀ persistence" value={fmt(snap.h0_total)} caption="components" />
        <Tile label="H₁ persistence" value={fmt(snap.h1_total)} caption="loops" />
        <Tile label="Bayesian θ" value={fmt(snap.bayesian_theta)} caption="P(high norm)" />
        <Tile
          label="changepoints"
          value={snap.changepoints.length > 0 ? snap.changepoints.join(", ") : "—"}
        />
        <Tile
          label="DP ε remaining"
          value={snap.dp_budget ? fmt(snap.dp_budget.epsilon_remaining, 3) : "—"}
          caption={
            snap.dp_budget
              ? `spent ${fmt(snap.dp_budget.epsilon_spent, 3)} / ${fmt(snap.dp_budget.epsilon_total, 1)}`
              : "DP off"
          }
        />
        <Tile
          label="Dilithium sigs verified"
          value={snap.signing_stats.verified.toLocaleString()}
          caption={
            snap.signing_stats.rejected > 0
              ? `${snap.signing_stats.rejected} rejected · ${snap.signing_stats.n_agents} agents`
              : `${snap.signing_stats.n_agents} agents · 0 rejected`
          }
        />
        <Tile
          label="BERTopic topics"
          value={snap.n_topics !== null ? String(snap.n_topics) : "—"}
          caption={
            snap.n_topics && snap.n_topics > 0
              ? `top: ${Object.values(snap.topic_top_words)[0]?.slice(0, 3).join(" / ") ?? ""}`
              : "warming up"
          }
        />
      </div>

      {summary && (
        <div className="rounded border border-slate-800 bg-slate-900/30 p-2 text-[11px] text-slate-300">
          95% CI: [{fmt(summary.ci95_low)}, {fmt(summary.ci95_high)}]
        </div>
      )}

      {(snap.h0_bars.length > 0 || snap.h1_bars.length > 0) && (
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-500">
            persistence barcode
          </div>
          <PersistenceBarcode h0Bars={snap.h0_bars} h1Bars={snap.h1_bars} />
        </div>
      )}
    </div>
  );
}
