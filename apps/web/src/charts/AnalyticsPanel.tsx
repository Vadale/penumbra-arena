/**
 * Streaming-analytics dashboard panel — DF-density + sparklines +
 * click-to-zoom detail modal.
 *
 * Each cell carries label + value + caption + 50px sparkline. A
 * click on the cell opens the DetailModal with a full-size chart
 * (LineChart for time-series scalars, TopicsBar for topics).
 */

import { useState } from "react";
import { useDashboardLive } from "../streams/dashboard";
import { DetailModal, type MetricKind } from "./DetailModal";
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
  onClick,
}: {
  label: string;
  value: string;
  caption?: string;
  history?: number[];
  accent?: boolean;
  ember?: boolean;
  onClick?: () => void;
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
    <button
      type="button"
      onClick={onClick}
      className="group w-full border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 text-left hover:border-[color:var(--color-penumbra-cyan)]"
      title={onClick ? "click for detail chart" : undefined}
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[9px] uppercase tracking-[0.15em] text-[color:var(--color-penumbra-dim)] group-hover:text-[color:var(--color-penumbra-muted)]">
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
    </button>
  );
}

export function AnalyticsPanel() {
  const { snap, history } = useDashboardLive();
  const [openMetric, setOpenMetric] = useState<MetricKind | null>(null);

  if (snap === null) {
    return (
      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
        analytics connecting<span className="animate-pulse">…</span>
      </div>
    );
  }

  const summary = snap.summary;
  const dpExhausted = snap.dp_budget !== null && snap.dp_budget.epsilon_remaining < 1.0;
  const open = (m: MetricKind) => setOpenMetric(m);
  const histories = history;

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 gap-1">
        <Cell
          label="traj.mean"
          value={fmt(summary?.mean ?? null)}
          caption={summary ? `n=${summary.n}` : undefined}
          history={histories.trajectory_mean}
          onClick={() => open("trajectory_mean")}
        />
        <Cell
          label="traj.std"
          value={fmt(summary?.std ?? null)}
          caption={summary ? `iqr=${fmt(summary.iqr)}` : undefined}
          history={histories.trajectory_std}
          onClick={() => open("trajectory_std")}
        />
        <Cell
          label="hdbscan"
          value={snap.hdbscan_n_clusters !== null ? String(snap.hdbscan_n_clusters) : "—"}
          caption={snap.hdbscan_n_noise !== null ? `noise=${snap.hdbscan_n_noise}` : undefined}
          history={histories.hdbscan_clusters}
          onClick={() => open("hdbscan_clusters")}
        />
        <Cell
          label="arima.next"
          value={fmt(snap.arima_next)}
          caption={snap.arima_std !== null ? `σ=${fmt(snap.arima_std)}` : undefined}
          history={histories.arima_next}
          onClick={() => open("arima_next")}
        />
        <Cell
          label="sinkhorn"
          value={fmt(snap.sinkhorn_cost)}
          caption="W₁"
          history={histories.sinkhorn_cost}
          onClick={() => open("sinkhorn_cost")}
        />
        <Cell
          label="var.95"
          value={fmt(snap.var95)}
          caption="tail risk"
          history={histories.var95}
          onClick={() => open("var95")}
        />
        <Cell
          label="h₀"
          value={fmt(snap.h0_total)}
          caption="components"
          history={histories.h0_total}
          onClick={() => open("h0_total")}
        />
        <Cell
          label="h₁"
          value={fmt(snap.h1_total)}
          caption="loops"
          history={histories.h1_total}
          onClick={() => open("h1_total")}
        />
        <Cell
          label="bayes.θ"
          value={fmt(snap.bayesian_theta)}
          caption="P(high‖)"
          history={histories.bayesian_theta}
          onClick={() => open("bayesian_theta")}
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
          history={histories.dp_epsilon_spent}
          ember={dpExhausted}
          accent={!!snap.dp_budget && !dpExhausted}
          onClick={() => open("dp_epsilon_spent")}
        />
        <Cell
          label="sigs.ok"
          value={snap.signing_stats.verified.toLocaleString()}
          caption={
            snap.signing_stats.rejected > 0
              ? `${snap.signing_stats.rejected} bad · ${snap.signing_stats.n_agents} ag`
              : `${snap.signing_stats.n_agents} ag · 0 bad`
          }
          history={histories.signing_verified}
          ember={snap.signing_stats.rejected > 0}
          accent
          onClick={() => open("signing_verified")}
        />
        <Cell
          label="topics"
          value={snap.n_topics !== null ? String(snap.n_topics) : "—"}
          caption={
            snap.n_topics && snap.n_topics > 0
              ? (Object.values(snap.topic_top_words)[0]?.slice(0, 3).join("·") ?? "")
              : "warming"
          }
          history={histories.n_topics}
          onClick={() => open("topics")}
        />
        <Cell
          label="pca λ₁"
          value={snap.pca?.eigenvalues[0] !== undefined ? fmt(snap.pca.eigenvalues[0]) : "—"}
          caption={
            snap.pca?.explained_variance_ratio
              ? `cum ${fmt((snap.pca.explained_variance_ratio[0] ?? 0) * 100, 0)}%`
              : "warming"
          }
          accent
          onClick={() => open("pca")}
        />
        <Cell
          label="logit β"
          value={snap.logit?.slope !== undefined ? fmt(snap.logit.slope, 3) : "—"}
          caption={
            snap.logit?.pseudo_r2 !== undefined
              ? `pseudo R² ${fmt(snap.logit.pseudo_r2, 2)}`
              : "warming"
          }
          accent
          onClick={() => open("logit")}
        />
        <Cell
          label="granger"
          value={(() => {
            const g = snap.granger;
            if (!g) return "—";
            const k = g.series_names.length + 1;
            const count = g.p_values.flat().filter((p, i) => p < 0.05 && i % k !== 0).length;
            return String(count);
          })()}
          caption={snap.granger ? "edges p<.05" : "warming"}
          accent
          onClick={() => open("granger")}
        />
        <Cell
          label="buys"
          value={snap.economy?.total_purchases.toLocaleString() ?? "—"}
          caption={
            snap.economy
              ? `${snap.economy.total_revenue.toFixed(0)} rev · ${Object.keys(snap.economy.category_counts).length} cats`
              : "warming"
          }
          accent
          onClick={() => open("economy")}
        />
        <Cell
          label="KM median"
          value={
            snap.survival && snap.survival.median_time !== null
              ? fmt(snap.survival.median_time, 0)
              : "—"
          }
          caption={
            snap.survival
              ? `${snap.survival.n_events} ev · ${snap.survival.n_censored} cens`
              : "warming"
          }
          accent
          onClick={() => open("survival")}
        />
        <Cell
          label="fiedler λ₂"
          value={snap.spectral ? fmt(snap.spectral.fiedler_value, 4) : "—"}
          caption={
            snap.spectral
              ? `${snap.spectral.n_nodes} nodes · ${snap.spectral.n_edges} edges`
              : "warming"
          }
          accent
          onClick={() => open("spectral")}
        />
        <Cell
          label="ATE (IPW)"
          value={snap.causal ? fmt(snap.causal.ipw_ate, 2) : "—"}
          caption={
            snap.causal
              ? `±${snap.causal.ipw_se.toFixed(2)} · ${snap.causal.n_treated}t/${snap.causal.n_control}c`
              : "warming"
          }
          accent
          onClick={() => open("causal")}
        />
        <Cell
          label="VAR p"
          value={snap.var_irf ? String(snap.var_irf.lag_order) : "—"}
          caption={
            snap.var_irf
              ? `${snap.var_irf.series_names.length}-var · h=${snap.var_irf.horizon}`
              : "warming"
          }
          accent
          onClick={() => open("var_irf")}
        />
        <Cell
          label="GARCH α+β"
          value={snap.garch ? fmt(snap.garch.persistence, 3) : "—"}
          caption={
            snap.garch
              ? `ω=${snap.garch.omega.toFixed(3)} · α=${snap.garch.alpha.toFixed(2)}`
              : "warming"
          }
          ember={!!snap.garch && snap.garch.persistence > 0.98}
          accent={!!snap.garch && snap.garch.persistence <= 0.98}
          onClick={() => open("garch")}
        />
        <Cell
          label="ANOVA F"
          value={snap.anova ? fmt(snap.anova.f_statistic, 2) : "—"}
          caption={
            snap.anova
              ? `p ${snap.anova.p_value < 0.001 ? "<.001" : snap.anova.p_value.toFixed(3)} · k=${snap.anova.group_names.length}`
              : "warming"
          }
          accent={!!snap.anova && snap.anova.p_value < 0.05}
          onClick={() => open("anova")}
        />
        <Cell
          label="ACF/PACF"
          value={snap.autocorrelation ? String(snap.autocorrelation.max_lag) : "—"}
          caption={
            snap.autocorrelation ? `band ±${snap.autocorrelation.conf_band.toFixed(3)}` : "warming"
          }
          accent
          onClick={() => open("autocorrelation")}
        />
        <Cell
          label="AUC"
          value={snap.roc ? fmt(snap.roc.auc, 3) : "—"}
          caption={snap.roc ? `${snap.roc.fpr.length} pts` : "warming"}
          accent={!!snap.roc && snap.roc.auc >= 0.7}
          ember={!!snap.roc && snap.roc.auc < 0.55}
          onClick={() => open("roc")}
        />
        <Cell
          label="corr"
          value={snap.correlations ? String(snap.correlations.series_names.length) : "—"}
          caption={snap.correlations ? `n=${snap.correlations.n_obs}` : "warming"}
          accent
          onClick={() => open("correlations")}
        />
        <Cell
          label="perm p"
          value={
            snap.permutation
              ? snap.permutation.p_two_sided < 0.001
                ? "<.001"
                : snap.permutation.p_two_sided.toFixed(3)
              : "—"
          }
          caption={snap.permutation ? `n=${snap.permutation.n_permutations}` : "warming"}
          ember={!!snap.permutation && snap.permutation.p_two_sided < 0.05}
          accent={!!snap.permutation && snap.permutation.p_two_sided >= 0.05}
          onClick={() => open("permutation")}
        />
        <Cell
          label="candles"
          value={
            snap.candles && snap.candles.length > 0
              ? String(snap.candles.reduce((s, c) => s + c.candles.length, 0))
              : "—"
          }
          caption={
            snap.candles && snap.candles.length > 0
              ? `${snap.candles.length} products · ${snap.candles[0]?.product_name ?? ""}`
              : "warming"
          }
          accent
          onClick={() => open("candles")}
        />
        <Cell
          label="CPI"
          value={
            snap.inflation && snap.inflation.cpi.length > 0
              ? (snap.inflation.cpi[snap.inflation.cpi.length - 1]?.[1] ?? 1).toFixed(3)
              : "—"
          }
          caption={(() => {
            const inf = snap.inflation;
            if (!inf || inf.cpi.length < 2) return "warming";
            const cpiNow = inf.cpi[inf.cpi.length - 1]?.[1] ?? 1;
            const cpiBase = inf.cpi[0]?.[1] ?? 1;
            const pct = ((cpiNow - cpiBase) / cpiBase) * 100;
            return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}% since t=${inf.cpi[0]?.[0] ?? 0}`;
          })()}
          accent
          onClick={() => open("inflation")}
        />
        <Cell
          label="Gini"
          value={snap.wealth ? snap.wealth.gini.toFixed(3) : "—"}
          caption={
            snap.wealth
              ? `${snap.wealth.n_agents} ag · p90 ${snap.wealth.p90.toFixed(1)}`
              : "warming"
          }
          ember={!!snap.wealth && snap.wealth.gini > 0.45}
          accent={!!snap.wealth && snap.wealth.gini <= 0.45}
          onClick={() => open("wealth")}
        />
        <Cell
          label="MAPPO π"
          value="inspect"
          caption="click agent's policy"
          accent
          onClick={() => open("policy_inspector")}
        />
        <Cell
          label="actions"
          value="live"
          caption="swarm choice mix"
          accent
          onClick={() => open("action_histogram")}
        />
        <Cell
          label="DP δ"
          value="clean ↔ noised"
          caption="privacy noise live"
          accent
          onClick={() => open("dp_compare")}
        />
        <Cell
          label="VRF leader"
          value="rotation"
          caption="chain consensus"
          accent
          onClick={() => open("vrf_leader")}
        />
        <Cell
          label="mempool"
          value="pending"
          caption="next block contents"
          accent
          onClick={() => open("mempool")}
        />
        <Cell
          label="ZK proof"
          value="verify"
          caption="Groth16 legal-path"
          accent
          onClick={() => open("zk_verify")}
        />
        <Cell
          label="BLS agg"
          value="inspect"
          caption="block signature"
          accent
          onClick={() => open("bls_aggregate")}
        />
        <Cell
          label="slash"
          value="forge evidence"
          caption="byzantine demo"
          ember
          onClick={() => open("slashing")}
        />
        <Cell
          label="training"
          value="live PPO"
          caption="start / stop / curves"
          accent
          onClick={() => open("training_curves")}
        />
        <Cell
          label="V(s)"
          value="critic"
          caption="value + entropy map"
          accent
          onClick={() => open("value_map")}
        />
        <Cell
          label="reward"
          value="shape"
          caption="tune objective live"
          accent
          onClick={() => open("reward_shaping")}
        />
        <Cell
          label="GAT attn"
          value="graph"
          caption="GATv2 attention"
          accent
          onClick={() => open("gat_attention")}
        />
        <Cell
          label="saliency"
          value="∂p/∂x"
          caption="feature gradient"
          accent
          onClick={() => open("saliency")}
        />
        <Cell
          label="CKKS"
          value="enc/dec"
          caption="HE round-trip"
          accent
          onClick={() => open("ckks_compare")}
        />
        <Cell
          label="Kyber"
          value="PQ KEM"
          caption="ML-KEM-768"
          accent
          onClick={() => open("kyber_kem")}
        />
        <Cell
          label="A/B π"
          value="multi-ckpt"
          caption="KL + agreement"
          accent
          onClick={() => open("multi_checkpoint")}
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

      <DetailModal
        open={openMetric !== null}
        onClose={() => setOpenMetric(null)}
        metric={openMetric}
        values={(() => {
          if (!openMetric) return undefined;
          // Metrics with a dedicated rich chart don't need the line.
          switch (openMetric) {
            case "pca":
            case "logit":
            case "granger":
            case "economy":
            case "survival":
            case "spectral":
            case "causal":
            case "var_irf":
            case "garch":
            case "anova":
            case "autocorrelation":
            case "roc":
            case "correlations":
            case "permutation":
            case "candles":
            case "inflation":
            case "wealth":
            case "policy_inspector":
            case "action_histogram":
            case "dp_compare":
            case "vrf_leader":
            case "mempool":
            case "zk_verify":
            case "bls_aggregate":
            case "slashing":
            case "training_curves":
            case "value_map":
            case "reward_shaping":
            case "gat_attention":
            case "saliency":
            case "ckks_compare":
            case "kyber_kem":
            case "multi_checkpoint":
              return undefined;
            default:
              return histories[mapMetricToHistoryKey(openMetric)];
          }
        })()}
        topicSizes={openMetric === "topics" ? snap.topic_sizes : undefined}
        topicTopWords={openMetric === "topics" ? snap.topic_top_words : undefined}
        regression={snap.regression}
        clusterScatter={snap.cluster_scatter}
        monteCarlo={snap.monte_carlo}
        pca={snap.pca}
        arima={snap.arima_forecast}
        logit={snap.logit}
        bayesian={snap.bayesian_posterior}
        granger={snap.granger}
        economy={snap.economy}
        survival={snap.survival}
        spectral={snap.spectral}
        causal={snap.causal}
        varIrf={snap.var_irf}
        garch={snap.garch}
        qqPoints={snap.qq_points}
        residualVsFitted={snap.residual_vs_fitted}
        anova={snap.anova}
        autocorrelation={snap.autocorrelation}
        roc={snap.roc}
        correlations={snap.correlations}
        permutation={snap.permutation}
        candles={snap.candles}
        inflation={snap.inflation}
        wealth={snap.wealth}
      />
    </div>
  );
}

function mapMetricToHistoryKey(
  m: Exclude<
    MetricKind,
    | "pca"
    | "logit"
    | "granger"
    | "economy"
    | "survival"
    | "spectral"
    | "causal"
    | "var_irf"
    | "garch"
    | "anova"
    | "autocorrelation"
    | "roc"
    | "correlations"
    | "permutation"
    | "candles"
    | "inflation"
    | "wealth"
    | "policy_inspector"
    | "action_histogram"
    | "dp_compare"
    | "vrf_leader"
    | "mempool"
    | "zk_verify"
    | "bls_aggregate"
    | "slashing"
    | "training_curves"
    | "value_map"
    | "reward_shaping"
    | "gat_attention"
    | "saliency"
    | "ckks_compare"
    | "kyber_kem"
    | "multi_checkpoint"
  >,
): keyof ReturnType<typeof useDashboardLive>["history"] {
  switch (m) {
    case "trajectory_mean":
      return "trajectory_mean";
    case "trajectory_std":
      return "trajectory_std";
    case "hdbscan_clusters":
      return "hdbscan_clusters";
    case "arima_next":
      return "arima_next";
    case "sinkhorn_cost":
      return "sinkhorn_cost";
    case "var95":
      return "var95";
    case "h0_total":
      return "h0_total";
    case "h1_total":
      return "h1_total";
    case "bayesian_theta":
      return "bayesian_theta";
    case "dp_epsilon_spent":
      return "dp_epsilon_spent";
    case "signing_verified":
      return "signing_verified";
    case "topics":
      return "n_topics";
  }
}
