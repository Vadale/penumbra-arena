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
        <Cell
          label="VDF"
          value="Wesolowski"
          caption="compute vs verify"
          accent
          onClick={() => open("vdf")}
        />
        <Cell
          label="Dilithium"
          value="agent sig"
          caption="PQ signature"
          accent
          onClick={() => open("dilithium")}
        />
        <Cell
          label="Shamir"
          value="(n, t)"
          caption="secret sharing"
          accent
          onClick={() => open("shamir")}
        />
        <Cell
          label="TFHE"
          value="LWE bits"
          caption="homomorphic gates"
          accent
          onClick={() => open("tfhe")}
        />
        <Cell
          label="snapshots"
          value="world"
          caption="save / load state"
          accent
          onClick={() => open("world_snapshot")}
        />
        <Cell
          label="arena 2D"
          value="graph"
          caption="force-directed"
          accent
          onClick={() => open("arena_graph")}
        />
        <Cell
          label="Pedersen"
          value="commit"
          caption="hide + bind + add"
          accent
          onClick={() => open("pedersen")}
        />
        <Cell
          label="Beaver"
          value="SMPC mul"
          caption="N-party multiplication"
          accent
          onClick={() => open("beaver")}
        />
        <Cell
          label="Schnorr ZK"
          value="Σ-protocol"
          caption="Fiat-Shamir proof"
          accent
          onClick={() => open("schnorr")}
        />
        <Cell
          label="ZK mul"
          value="circom"
          caption="a·b === c"
          accent
          onClick={() => open("zk_multiplier")}
        />
        <Cell
          label="forge"
          value="snark attack"
          caption="verifier must reject"
          ember
          onClick={() => open("snark_forge")}
        />
      </div>

      <div className="grid grid-cols-2 gap-1">
        <Cell
          label="logistics — fill rate"
          value="served / requested"
          caption="end-customer demand vs inventory"
          accent
          onClick={() => open("logistics_fill_rate")}
        />
        <Cell
          label="logistics — inventory"
          value="health"
          caption="stockouts + holding cost"
          onClick={() => open("logistics_inventory_health")}
        />
        <Cell
          label="logistics — orders"
          value="(s, S) book"
          caption="pending + lead-time stats"
          onClick={() => open("logistics_orders")}
        />
        <Cell
          label="logistics — reorder"
          value="(s, S) policy"
          caption="tweak s/S fractions"
          onClick={() => open("logistics_reorder_policy")}
        />
        <Cell
          label="logistics — capacity"
          value="cargo util"
          caption="fleet utilisation"
          onClick={() => open("logistics_capacity")}
        />
        <Cell
          label="logistics — VRP"
          value="OR baseline"
          caption="solver vs actual gap"
          accent
          onClick={() => open("logistics_vrp")}
        />
        <Cell
          label="logistics — echelon"
          value="bullwhip"
          caption="supplier → distributor → city"
          accent
          onClick={() => open("logistics_echelon")}
        />
        <Cell
          label="logistics — dispatch"
          value="carriers + rewards"
          caption="greedy assignment + earnings"
          accent
          onClick={() => open("logistics_dispatch")}
        />
        <Cell
          label="federated learning"
          value="FedAvg + CKKS"
          caption="encrypted aggregation"
          accent
          onClick={() => open("federated_status")}
        />
        <Cell
          label="event bus"
          value="cross-pillar"
          caption="signals propagating"
          accent
          onClick={() => open("event_bus")}
        />
        <Cell
          label="event graph"
          value="producer → consumer"
          caption="kinds + handler latency"
          accent
          onClick={() => open("event_graph")}
        />
        <Cell
          label="security — blocked"
          value="signing rejected"
          caption="market + logistics + FL gated"
          accent
          onClick={() => open("security_blocked")}
        />
        <Cell
          label="defense — decoy"
          value="data poisoning"
          caption="attacker fits contaminated stream"
          accent
          onClick={() => open("defense_data_poisoning")}
        />
        <Cell
          label="defense — padding"
          value="bucket + cover"
          caption="sizes → 1, Poisson arrivals"
          accent
          onClick={() => open("defense_padding")}
        />
        <Cell
          label="defense — k-anon"
          value="suppression"
          caption="adv ≤ 1/k"
          accent
          onClick={() => open("defense_k_anonymity")}
        />
        <Cell
          label="defense — ℓ-div"
          value="distinct sensitive"
          caption="homogeneity-safe"
          accent
          onClick={() => open("defense_l_diversity")}
        />
        <Cell
          label="defense — GAN"
          value="synth trace"
          caption="Gaussian stub; CycleGAN deferred"
          accent
          onClick={() => open("defense_gan")}
        />
        <Cell
          label="defense — obfusc."
          value="Bonferroni + dummies"
          caption="drain attacker DP budget"
          accent
          onClick={() => open("defense_request_obfuscation")}
        />
        <Cell
          label="attack — fingerprint"
          value="1-NN behavioural"
          caption="re-id across matches"
          accent
          onClick={() => open("attack_agent_fingerprint")}
        />
        <Cell
          label="attack — trajectory"
          value="HMM Baum-Welch"
          caption="temporal action structure"
          accent
          onClick={() => open("attack_trajectory_fingerprint")}
        />
        <Cell
          label="attack — membership"
          value="Shokri shadows"
          caption="was sample in training?"
          accent
          onClick={() => open("attack_membership_inference")}
        />
        <Cell
          label="attack — model inv."
          value="grad leakage"
          caption="reconstruct from ∇"
          accent
          onClick={() => open("attack_model_inversion")}
        />
        <Cell
          label="attack — reward poison"
          value="5% backdoor"
          caption="REINFORCE drifts"
          accent
          onClick={() => open("attack_reward_poisoning")}
        />
        <Cell
          label="attack — cache timing"
          value="CKKS const-time"
          caption="must FAIL on TenSEAL"
          accent
          onClick={() => open("attack_cache_sidechannel")}
        />
        <Cell
          label="operator — scenarios"
          value="12 starter drills"
          caption="tabletop exercises"
          ember
          onClick={() => open("operator_scenarios")}
        />
        <Cell
          label="custom policy"
          value="sandboxed injection"
          caption="try + adopt + remove"
          accent
          onClick={() => open("custom_policy")}
        />
        <Cell
          label="capture-the-flag"
          value="5 challenges"
          caption="leaderboard per id"
          accent
          onClick={() => open("ctf")}
        />
        <Cell
          label="story mode"
          value="8 stories"
          caption="cross-pillar lessons"
          accent
          onClick={() => open("story_mode")}
        />
        <Cell
          label="world — branches"
          value="pickle clones"
          caption="N branches · side-by-side"
          accent
          onClick={() => open("world_branches")}
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
            case "vdf":
            case "dilithium":
            case "shamir":
            case "tfhe":
            case "world_snapshot":
            case "arena_graph":
            case "pedersen":
            case "beaver":
            case "schnorr":
            case "zk_multiplier":
            case "snark_forge":
            case "logistics_fill_rate":
            case "logistics_inventory_health":
            case "logistics_orders":
            case "logistics_reorder_policy":
            case "logistics_capacity":
            case "logistics_vrp":
            case "logistics_echelon":
            case "logistics_dispatch":
            case "federated_status":
            case "event_bus":
            case "event_graph":
            case "security_blocked":
            case "defense_data_poisoning":
            case "defense_padding":
            case "defense_k_anonymity":
            case "defense_l_diversity":
            case "defense_gan":
            case "defense_request_obfuscation":
            case "frost":
            case "sphincs":
            case "verkle":
            case "bbs_plus":
            case "threshold_ecdsa":
            case "yao":
            case "psi":
            case "mix_net":
            case "attack_agent_fingerprint":
            case "attack_trajectory_fingerprint":
            case "operator_scenarios":
            case "attack_membership_inference":
            case "attack_model_inversion":
            case "attack_reward_poisoning":
            case "attack_cache_sidechannel":
            case "custom_policy":
            case "ctf":
            case "story_mode":
            case "world_branches":
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
    | "vdf"
    | "dilithium"
    | "shamir"
    | "tfhe"
    | "world_snapshot"
    | "arena_graph"
    | "pedersen"
    | "beaver"
    | "schnorr"
    | "zk_multiplier"
    | "snark_forge"
    | "logistics_fill_rate"
    | "logistics_inventory_health"
    | "logistics_orders"
    | "logistics_reorder_policy"
    | "logistics_capacity"
    | "logistics_vrp"
    | "logistics_echelon"
    | "logistics_dispatch"
    | "federated_status"
    | "event_bus"
    | "event_graph"
    | "security_blocked"
    | "defense_data_poisoning"
    | "defense_padding"
    | "defense_k_anonymity"
    | "defense_l_diversity"
    | "defense_gan"
    | "defense_request_obfuscation"
    | "frost"
    | "sphincs"
    | "verkle"
    | "bbs_plus"
    | "threshold_ecdsa"
    | "yao"
    | "psi"
    | "mix_net"
    | "attack_agent_fingerprint"
    | "attack_trajectory_fingerprint"
    | "attack_membership_inference"
    | "attack_model_inversion"
    | "attack_reward_poisoning"
    | "attack_cache_sidechannel"
    | "operator_scenarios"
    | "custom_policy"
    | "ctf"
    | "world_branches"
    | "story_mode"
    | "operator_leaderboard"
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
