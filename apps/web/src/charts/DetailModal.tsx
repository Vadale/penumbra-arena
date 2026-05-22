/**
 * Modal that pops up when the user clicks an AnalyticsPanel cell.
 *
 * Per-metric chart routing:
 *   trajectory_mean → RegressionChart (OLS + R² + 95% band)
 *   hdbscan_clusters → ClusterScatter (PC1/PC2 with HDBSCAN labels)
 *   var95            → MonteCarloFan (bootstrap percentile band + VaR/CVaR)
 *   pca              → PCAScree (eigenvalues + cumulative variance)
 *   topics           → TopicsBar
 *   everything else  → LineChart (generic time-series)
 *
 * Dismiss via Escape, backdrop click, or the explicit close button.
 */

import { useEffect } from "react";
import type {
  ANOVAReport as ANOVAReportData,
  ArimaForecast as ArimaForecastData,
  AutocorrelationReport as AutocorrelationReportData,
  BayesianPosterior as BayesianPosteriorData,
  CandleSeries as CandleSeriesData,
  CausalEstimate as CausalEstimateData,
  ClusterScatter as ClusterScatterData,
  CorrelationMatrix as CorrelationMatrixData,
  EconomySnapshot as EconomySnapshotData,
  GarchResult as GarchResultData,
  GrangerMatrix as GrangerMatrixData,
  InflationSeries as InflationSeriesData,
  LogitResult as LogitResultData,
  MonteCarloFan as MCFanData,
  PCAResult,
  PermutationReport as PermutationReportData,
  RegressionFit,
  ROCData as ROCDataType,
  SpectralReport as SpectralReportData,
  SurvivalCurve as SurvivalCurveData,
  VARImpulseResponse as VARImpulseResponseData,
  WealthReport as WealthReportData,
} from "../streams/dashboard";
import { useActionHistogram } from "../streams/learning";
import { ACFChart } from "./ACFChart";
import { ActionHistogramChart } from "./ActionHistogramChart";
import { ANOVAChart } from "./ANOVAChart";
import { ArimaChart } from "./ArimaChart";
import { BayesianDensity } from "./BayesianDensity";
import { BLSChart } from "./BLSChart";
import { CandlestickChart } from "./CandlestickChart";
import { CausalChart } from "./CausalChart";
import { ClusterScatter } from "./ClusterScatter";
import { CorrelationHeatmap } from "./CorrelationHeatmap";
import { DpCompareChart } from "./DpCompareChart";
import { EconomyChart } from "./EconomyChart";
import { GarchChart } from "./GarchChart";
import { GrangerMatrix } from "./GrangerMatrix";
import { InflationChart } from "./InflationChart";
import { LineChart } from "./LineChart";
import { LogitChart } from "./LogitChart";
import { MempoolChart } from "./MempoolChart";
import { MonteCarloFan } from "./MonteCarloFan";
import { PCAScree } from "./PCAScree";
import { PermutationChart } from "./PermutationChart";
import { PolicyInspector } from "./PolicyInspector";
import { RegressionChart } from "./RegressionChart";
import { RewardShapingChart } from "./RewardShapingChart";
import { ROCChart } from "./ROCChart";
import { SlashingChart } from "./SlashingChart";
import { SpectralChart } from "./SpectralChart";
import { SurvivalChart } from "./SurvivalChart";
import { TopicsBar } from "./TopicsBar";
import { TrainingCurves } from "./TrainingCurves";
import { ValueMapChart } from "./ValueMapChart";
import { VarIrfChart } from "./VarIrfChart";
import { VRFLeaderChart } from "./VRFLeaderChart";
import { WealthChart } from "./WealthChart";
import { ZKVerifyChart } from "./ZKVerifyChart";

export type MetricKind =
  | "trajectory_mean"
  | "trajectory_std"
  | "hdbscan_clusters"
  | "arima_next"
  | "sinkhorn_cost"
  | "var95"
  | "h0_total"
  | "h1_total"
  | "bayesian_theta"
  | "dp_epsilon_spent"
  | "signing_verified"
  | "topics"
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
  | "reward_shaping";

interface Props {
  open: boolean;
  onClose: () => void;
  metric: MetricKind | null;
  values?: number[];
  topicSizes?: Record<string, number>;
  topicTopWords?: Record<string, string[]>;
  regression?: RegressionFit | null;
  clusterScatter?: ClusterScatterData | null;
  monteCarlo?: MCFanData | null;
  pca?: PCAResult | null;
  arima?: ArimaForecastData | null;
  logit?: LogitResultData | null;
  bayesian?: BayesianPosteriorData | null;
  granger?: GrangerMatrixData | null;
  economy?: EconomySnapshotData | null;
  survival?: SurvivalCurveData | null;
  spectral?: SpectralReportData | null;
  causal?: CausalEstimateData | null;
  varIrf?: VARImpulseResponseData | null;
  garch?: GarchResultData | null;
  qqPoints?: [number, number][];
  residualVsFitted?: [number, number][];
  anova?: ANOVAReportData | null;
  autocorrelation?: AutocorrelationReportData | null;
  roc?: ROCDataType | null;
  correlations?: CorrelationMatrixData | null;
  permutation?: PermutationReportData | null;
  candles?: CandleSeriesData[];
  inflation?: InflationSeriesData | null;
  wealth?: WealthReportData | null;
}

const META: Record<MetricKind, { label: string; description: string; yUnit?: string }> = {
  trajectory_mean: {
    label: "trajectory mean — OLS regression on tick",
    description:
      "OLS fit y_t = α + β·t over the most recent window of trajectory L₂ norms. β = slope (per-tick drift), R² = fraction of variance explained, σ = residual std error, shaded band = ±1.96σ ≈ 95% prediction interval. The interesting reading isn't the absolute slope — it's whether the residuals stay small (high R²) or scatter widely (low R²).",
  },
  trajectory_std: {
    label: "trajectory std",
    description: "standard deviation of the same trajectory series; a measure of swarm dispersion.",
  },
  hdbscan_clusters: {
    label: "HDBSCAN clusters on PC1/PC2",
    description:
      "Agents projected onto the first two principal components of their position history. HDBSCAN clusters that 2-D embedding without requiring a fixed number of factions. Noise points (label = -1) are agents whose movement pattern is too idiosyncratic to belong to any group.",
  },
  arima_next: {
    label: "ARIMA(1,0,0) forecast with 95% PI",
    description:
      "AR(1) one-step-ahead forecast of the trajectory norm. The dashed cyan extension is the point forecast ŷ_{t+1}; the wedge is the ±1.96σ prediction interval. Pedagogically: AR(1) is the simplest non-trivial time-series model — ŷ_t = c + φ·y_{t-1} + ε. Wide PI = high σ = uncertain forecast.",
  },
  sinkhorn_cost: {
    label: "Sinkhorn / W₁ cost",
    description:
      "regularised optimal transport between successive encrypted-heatmap snapshots. Large = the density shifted between samples.",
  },
  var95: {
    label: "Bootstrap fan + VaR/CVaR(95%)",
    description:
      "Stationary block bootstrap (n=400) of the trajectory norm mean. Inner band [25%, 75%], outer band [5%, 95%], median in cyan. VaR(.95) is the 95th-percentile loss boundary; CVaR(.95) is the expected loss CONDITIONAL on exceeding VaR — the average tail loss. Pedagogically: CVaR is the coherent risk measure, VaR is the historical legacy one.",
  },
  h0_total: {
    label: "H₀ total persistence",
    description:
      "sum of lifetimes of connected components in the Vietoris-Rips filtration over agent positions.",
  },
  h1_total: {
    label: "H₁ total persistence",
    description:
      "sum of lifetimes of 1-dimensional holes (loops) in the same filtration. Spikes = coalition rings forming.",
  },
  bayesian_theta: {
    label: "Bayesian posterior — Beta(α, β)",
    description:
      "Posterior density for θ = P(trajectory_norm > median) under a Beta(1, 1) prior + Binomial likelihood. Closed-form posterior Beta(1+s, 1+n-s). Cyan band = 95% credible interval. Pedagogically: a credible interval is a probability statement about the parameter, unlike a frequentist confidence interval which is a coverage statement about the procedure.",
  },
  dp_epsilon_spent: {
    label: "Differential-privacy ε spent",
    description:
      "cumulative privacy budget consumed by Laplace-noised heatmap releases. Saturates and then the system falls back to clean releases.",
  },
  signing_verified: {
    label: "Dilithium signatures verified",
    description:
      "cumulative count of per-tick ML-DSA-65 signature verifications across all agents. Grows linearly; rejected count tracked separately.",
  },
  topics: {
    label: "BERTopic topics",
    description:
      "number of topics surfaced over the agent-utterance corpus. Sizes shown by bar; representative words listed next to each bar.",
  },
  pca: {
    label: "PCA — eigenvalues + cumulative variance",
    description:
      "Eigendecomposition of the position-history covariance. Bars = top eigenvalues λ₁..λ₈; line = cumulative explained-variance ratio; red dashed line = Kaiser criterion (λ = 1). The number of components above Kaiser is the standard heuristic for 'intrinsic dimensionality'; the 90% cumulative point is the variance-retention rule of thumb for downstream models.",
  },
  logit: {
    label: "Logistic regression — propensity",
    description:
      "P(y_t > median | y_{t-1}) under L2-regularised logistic regression. The sigmoid σ(α + β·x) shows how the lag-1 value predicts being-above-median next tick. Cyan dots are treated cases (y=1, top edge), ember dots are untreated (y=0, bottom edge). The vertical dashed line marks p = 0.5 (decision boundary). Pseudo-R² is McFadden's: 1 - LL/LL₀; > 0.2 is already a strong fit in binary settings.",
  },
  granger: {
    label: "Granger causality matrix",
    description:
      "Pairwise F-test p-values for the null 'row series does NOT Granger-cause column series' at the configured lag. Series: traj (trajectory norm), vol (|Δtraj|), disp (distinct nodes occupied), entropy (heatmap entropy). Low p (cyan) ⇒ past values of the row series help predict the column series beyond what the column's own lags would. Causality here is in the predictive sense, not the philosophical one.",
  },
  economy: {
    label: "City economy — purchases stream",
    description:
      "Every city stocks 10 of 30 catalogue products (food, hygiene, tools, luxury, medicine). When an agent arrives at a city it Bernoulli(p=.06)-rolls each item; a hit fires a Geometric(1/1.5) quantity purchase. The aggregates here feed regression/Granger/etc with a second semantically distinct stream, so the live charts stop being just a function of the trajectory norm.",
  },
  survival: {
    label: "Kaplan-Meier — match duration",
    description:
      "Non-parametric estimate of P(match still running at tick t). Each match is observed if it ended with a winner ('death'); censored if it was cut for any other reason. The cyan band is the pointwise 95% CI. The dashed ember line marks the median survival time. Pedagogically: KM is what you reach for whenever you have time-to-event data with right-censoring, which is most real-world reliability + medical data.",
  },
  spectral: {
    label: "Laplacian spectrum + Fiedler vector",
    description:
      "Bottom eigenvalues of the arena's normalised Laplacian L_sym = I - D^{-1/2} A D^{-1/2}. The smallest (λ₂, Fiedler value) measures algebraic connectivity — 0 means disconnected, large means a robust mesh. The Fiedler EIGENVECTOR gives the optimal continuous relaxation of the min-cut partition: sign(v_i) tells you which 'side' of the graph node i lives on. Bars: top eigenvalues. Lower: per-node Fiedler vector colored by sign.",
  },
  causal: {
    label: "Causal — IPW + AIPW ATE",
    description:
      "Average Treatment Effect of 'agent purchased ≥1 luxury item in the window' on the agent's trajectory L2 distance. Two estimators side by side: IPW (Rosenbaum-Rubin propensity reweighting) and AIPW (doubly robust). The histogram shows the propensity-score distributions per group — visual check of the positivity / overlap assumption (treated and control should have overlapping support).",
  },
  var_irf: {
    label: "VAR — impulse response grid",
    description:
      "Fit a Vector AutoRegression VAR(p) over (traj, vol, disp). Each cell (i, j) shows how a 1-σ shock in series i at t=0 propagates into series j over the next 10 steps. Diagonal cells (ember) show how a shock persists in its own series; off-diagonal cells (cyan) show the cross-series spillover. Pedagogically: IRFs make the IMPLIED dynamics of the fit explicit, which raw VAR coefficients hide.",
  },
  garch: {
    label: "GARCH(1, 1) — conditional volatility",
    description:
      "σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1} fit on the log-returns of the trajectory norm. The cyan band is ±σ_t (the model's evolving volatility), the white line is the observed log-returns. Persistence = α + β; values close to 1.0 indicate near-integrated GARCH (shocks decay very slowly). Pedagogically: this is THE workhorse for conditional volatility in finance, and the right baseline before you reach for stochastic-vol models.",
  },
  anova: {
    label: "ANOVA — F-test across HDBSCAN clusters",
    description:
      "One-way ANOVA on the per-agent PC1-PC2 norm, grouped by HDBSCAN cluster label. The F-statistic compares between-group variance to within-group variance under the null 'all group means are equal'. Small p ⇒ at least one pair of clusters has a different mean position. ANOVA does NOT tell you WHICH pair (you'd need Tukey HSD or pairwise t-tests for that). Cyan dots = group means; bars = 95% CI; ember dashed = grand mean.",
  },
  autocorrelation: {
    label: "ACF + PACF — ARIMA order diagnostics",
    description:
      "Standard diagnostic for choosing ARIMA(p, d, q) order on the trajectory series. ACF (top) is autocorrelation across all lags — geometric decay ⇒ AR process. PACF (bottom) is partial autocorrelation controlling for shorter lags — cuts off at lag p for an AR(p). Cyan band = ±1.96/√n significance bounds. Bars OUTSIDE the band are significant at the 5% level.",
  },
  roc: {
    label: "ROC curve + AUC — logit classifier",
    description:
      "ROC plots TPR (sensitivity) vs FPR (1 - specificity) as the threshold sweeps. AUC = area under it; 0.5 = random, 1.0 = perfect, > 0.7 = useful. Ember dashed = random reference. The cyan-filled region quantifies the discrimination the trained logit achieves on the latest data window.",
  },
  correlations: {
    label: "Correlation heatmap — Pearson + Spearman",
    description:
      "Two K×K matrices across (traj, vol, traj², disp). Pearson r captures LINEAR association; Spearman ρ captures MONOTONE association. They diverge when the relationship is monotone but non-linear — comparing them is a quick non-parametric robustness check. Cyan = positive, ember = negative; intensity ∝ |r|.",
  },
  permutation: {
    label: "Permutation test — null ATE distribution",
    description:
      "Shuffle the treatment labels n times and recompute the simple ATE under each shuffle; the histogram is the empirical null distribution. The white vertical line is the OBSERVED ATE on real treatment assignments. Two-sided p = P(|null| ≥ |observed|). Pedagogically: a permutation p-value makes ZERO parametric assumptions — it's exact under the null exchangeability hypothesis.",
  },
  candles: {
    label: "Candlestick — OHLC per product",
    description:
      "For the top-3 most-traded products, group trades into 20-tick buckets and draw a candle: body open→close (cyan if up, ember if down), wick low→high. Volume is the total quantity traded in the bucket. Click a product chip above to switch. Pedagogically: candlesticks are the standard way to read price action — body length + colour show net move, wick length shows intra-period volatility.",
  },
  inflation: {
    label: "CPI + money supply",
    description:
      "Twin-axis line chart. Cyan = CPI (Laspeyres index over all stocked products, base = 1.0). Ember = total coins in agent wallets + city treasuries (money is CONSERVED in this market — no minting). When CPI rises while money supply is flat, the inflation is pure supply/demand on a fixed M. Pedagogically: this isolates the relative-price mechanism from the monetary one — most textbook treatments conflate them.",
  },
  wealth: {
    label: "Wealth distribution — Lorenz + Gini",
    description:
      "Lorenz curve: cumulative agent share (x) vs cumulative wealth share (y). The ember 45° line is perfect equality; the cyan curve is the actual distribution; the shaded area between them is the Gini half-area (Gini = 2 × area). Gini = 0 means everyone owns the same; Gini = 1 means one agent owns everything. The percentile readouts (p10/p50/p90/p99) make the tail visible — a Gini around 0.3 with p99 much higher than p90 signals fat-tailed wealth.",
  },
  policy_inspector: {
    label: "MAPPO policy inspector",
    description:
      "Live introspection of the actor network. Pick any agent id and see the observation it's receiving (cost-to-neighbour + is-goal features), the actor's post-softmax action probabilities at the current temperature, and the action it would CHOOSE (highlighted bar). The labels '→ #N' = move to neighbour-N; 'stay' = no-op. Adjust temperature in the status bar to watch the distribution flatten or sharpen in real time.",
  },
  action_histogram: {
    label: "Action histogram — swarm-wide",
    description:
      "Histogram of the actions chosen on the current tick across ALL 50 agents. 'neigh i' = moved to the i-th sorted neighbour; 'stay' = no move; 'random' = the MAPPO toggle is OFF and the simulation is using random walk. With high temperature you see a more uniform distribution; with low temperature the chosen-action mode dominates.",
  },
  dp_compare: {
    label: "DP — clean vs noised heatmap",
    description:
      "Side-by-side: the CLEAN encrypted-heatmap aggregate (cyan, pre-DP) and the RELEASED density (ember, after Laplace noise). The δ panel shows the raw noise vector (released − clean). The L1/L2 readouts quantify the injected privacy noise. This is normally invisible from outside the server; we expose it here so you can SEE the privacy/utility tradeoff DP is making.",
  },
  vrf_leader: {
    label: "VRF leader rotation",
    description:
      "Every block, the validators run a VRF lottery using the previous block hash + height as the seed. Each computes a deterministic VRF output from its secret key; the smallest output wins. Pedagogically: this gives PoS its leader-election property — unbiasable, publicly verifiable, and decentralisable. The leader-frequency bars confirm the lottery is roughly fair.",
  },
  mempool: {
    label: "Mempool — pending transactions",
    description:
      "Match outcomes accumulate here when matches end; slashing evidence accumulates here when an equivocation is submitted. The next BLS-finalised block drains up to max_payload of these. If a match just ended (status=won), expect an outcome to appear briefly.",
  },
  zk_verify: {
    label: "Groth16 — legal-path proof verification",
    description:
      "Loads the shipped circuit artifacts and runs our pure-Python Groth16 verifier. The honest case ACCEPTS; tampering the public goal id or one adjacency bit causes the verifier to REJECT — proving the proof is BOUND to the published public inputs. The circuit semantic: 'I know an intermediate node such that (start → mid → goal) is a legal walk in the 4×4 arena.'",
  },
  bls_aggregate: {
    label: "BLS aggregate signature",
    description:
      "N validators each sign the same block_hash + height payload with their BLS12-381 secret. The chain stores ONE 96-byte aggregate signature point instead of N individual ones. fast_aggregate_verify against the validator pubkeys re-establishes finality. Tamper the block contents and the verifier rejects — the aggregate binds to the exact payload.",
  },
  slashing: {
    label: "Slashing — submit equivocation evidence",
    description:
      "Pick an active validator and the demo server signs two CONFLICTING block hashes with that validator's secret key, then files the SlashingEvidence. The chain folds the result into the next block — the offender's pubkey moves into slashed_pubkeys, active_indices shrinks, and future blocks finalise with the remaining quorum. This is gated behind PENUMBRA_DEMO_SELF_SLASH=1 so production-shaped runs can't accidentally enable it.",
  },
  training_curves: {
    label: "Live MAPPO training — start/stop + curves",
    description:
      "Click START and a background asyncio task begins running PPO updates against the SAME actor that drives the live arena. Each iteration: rollout 64 steps in an internal env, compute GAE advantages, run 4 PPO epochs, append (actor_loss, critic_loss, entropy, KL, mean_reward) to the curves below. The live policy mutates in real time.",
  },
  value_map: {
    label: "Critic V(s) + per-node policy entropy",
    description:
      "V(s) (top stat) is the critic's estimate of expected future return for the current global state. The per-node bars show the average actor entropy of agents at that node — low entropy = confident decision, high entropy (ember) = uncertain.",
  },
  reward_shaping: {
    label: "Reward shaping — tune the objective live",
    description:
      "Sliders mutate the shared RewardWeights singleton used by the training env. Background PPO picks up new values on its NEXT iteration. Try crowding=-0.05 (penalise the swarm clumping) and watch the policy spread the agents out.",
  },
};

export function DetailModal({
  open,
  onClose,
  metric,
  values,
  topicSizes,
  topicTopWords,
  regression,
  clusterScatter,
  monteCarlo,
  pca,
  arima,
  logit,
  bayesian,
  granger,
  economy,
  survival,
  spectral,
  causal,
  varIrf,
  garch,
  qqPoints,
  residualVsFitted,
  anova,
  autocorrelation,
  roc,
  correlations,
  permutation,
  candles,
  inflation,
  wealth,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
    };
  }, [open, onClose]);

  if (!open || metric === null) return null;
  const meta = META[metric];

  const body = (() => {
    if (metric === "topics") {
      return <TopicsBar topicSizes={topicSizes ?? {}} topWords={topicTopWords ?? {}} />;
    }
    if (metric === "trajectory_mean" && regression) {
      return (
        <RegressionChart fit={regression} qqPoints={qqPoints} residualVsFitted={residualVsFitted} />
      );
    }
    if (metric === "hdbscan_clusters" && clusterScatter) {
      return <ClusterScatter data={clusterScatter} />;
    }
    if (metric === "var95" && monteCarlo) {
      return <MonteCarloFan fan={monteCarlo} />;
    }
    if (metric === "pca" && pca) {
      return <PCAScree pca={pca} />;
    }
    if (metric === "arima_next" && arima) {
      return <ArimaChart data={arima} />;
    }
    if (metric === "logit" && logit) {
      return <LogitChart data={logit} />;
    }
    if (metric === "bayesian_theta" && bayesian) {
      return <BayesianDensity data={bayesian} />;
    }
    if (metric === "granger" && granger) {
      return <GrangerMatrix data={granger} />;
    }
    if (metric === "economy" && economy) {
      return <EconomyChart data={economy} />;
    }
    if (metric === "survival" && survival) {
      return <SurvivalChart data={survival} />;
    }
    if (metric === "spectral" && spectral) {
      return <SpectralChart data={spectral} />;
    }
    if (metric === "causal" && causal) {
      return <CausalChart data={causal} />;
    }
    if (metric === "var_irf" && varIrf) {
      return <VarIrfChart data={varIrf} />;
    }
    if (metric === "garch" && garch) {
      return <GarchChart data={garch} />;
    }
    if (metric === "anova" && anova) {
      return <ANOVAChart data={anova} />;
    }
    if (metric === "autocorrelation" && autocorrelation) {
      return <ACFChart data={autocorrelation} />;
    }
    if (metric === "roc" && roc) {
      return <ROCChart data={roc} />;
    }
    if (metric === "correlations" && correlations) {
      return <CorrelationHeatmap data={correlations} />;
    }
    if (metric === "permutation" && permutation) {
      return <PermutationChart data={permutation} />;
    }
    if (metric === "candles" && candles && candles.length > 0) {
      return <CandlestickChart series={candles} />;
    }
    if (metric === "inflation" && inflation) {
      return <InflationChart data={inflation} />;
    }
    if (metric === "wealth" && wealth) {
      return <WealthChart data={wealth} />;
    }
    if (metric === "policy_inspector") {
      return <PolicyInspector />;
    }
    if (metric === "action_histogram") {
      return <ActionHistogramInline />;
    }
    if (metric === "dp_compare") {
      return <DpCompareChart />;
    }
    if (metric === "vrf_leader") {
      return <VRFLeaderChart />;
    }
    if (metric === "mempool") {
      return <MempoolChart />;
    }
    if (metric === "zk_verify") {
      return <ZKVerifyChart />;
    }
    if (metric === "bls_aggregate") {
      return <BLSChart />;
    }
    if (metric === "slashing") {
      return <SlashingChart />;
    }
    if (metric === "training_curves") {
      return <TrainingCurves />;
    }
    if (metric === "value_map") {
      return <ValueMapChart />;
    }
    if (metric === "reward_shaping") {
      return <RewardShapingChart />;
    }
    return <LineChart values={values ?? []} label={meta.label} yUnit={meta.yUnit} />;
  })();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6">
      <button
        type="button"
        aria-label="dismiss detail"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-transparent"
      />
      <div
        className="relative w-full max-w-2xl border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] p-5 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label={meta.label}
      >
        <div className="mb-3 flex items-baseline justify-between">
          <div className="text-xs uppercase tracking-[0.25em] text-[color:var(--color-penumbra-cyan)]">
            {meta.label}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-[11px] text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-text)]"
          >
            esc
          </button>
        </div>
        <p className="mb-4 text-[11px] leading-relaxed text-[color:var(--color-penumbra-muted)]">
          {meta.description}
        </p>
        <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-3">
          {body}
        </div>
      </div>
    </div>
  );
}

/** Inline wrapper for the live action histogram polling hook. */
function ActionHistogramInline() {
  const data = useActionHistogram();
  if (!data) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        action histogram warming up
      </div>
    );
  }
  return <ActionHistogramChart data={data} />;
}
