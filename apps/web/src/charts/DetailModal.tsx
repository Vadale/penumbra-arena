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

import { useEffect, useRef } from "react";
import { useFocusTrap } from "../hooks/useFocusTrap";
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
import { ArenaGraphChart } from "./ArenaGraphChart";
import { ArimaChart } from "./ArimaChart";
import { AttackAgentFingerprintChart } from "./AttackAgentFingerprintChart";
import { AttackCacheSidechannelChart } from "./AttackCacheSidechannelChart";
import { AttackMembershipInferenceChart } from "./AttackMembershipInferenceChart";
import { AttackModelInversionChart } from "./AttackModelInversionChart";
import { AttackRewardPoisoningChart } from "./AttackRewardPoisoningChart";
import { AttackTrajectoryFingerprintChart } from "./AttackTrajectoryFingerprintChart";
import { BayesianDensity } from "./BayesianDensity";
import { BBSPlusChart } from "./BBSPlusChart";
import { BeaverChart } from "./BeaverChart";
import { BLSChart } from "./BLSChart";
import { BlockedAgentsChart } from "./BlockedAgentsChart";
import { CandlestickChart } from "./CandlestickChart";
import { CausalChart } from "./CausalChart";
import { CKKSCompareChart } from "./CKKSCompareChart";
import { ClusterScatter } from "./ClusterScatter";
import { CorrelationHeatmap } from "./CorrelationHeatmap";
import { CTFChart } from "./CTFChart";
import { CustomPolicyChart } from "./CustomPolicyChart";
import { DefenseDataPoisoningChart } from "./DefenseDataPoisoningChart";
import { DefenseGANChart } from "./DefenseGANChart";
import { DefenseKAnonymityChart } from "./DefenseKAnonymityChart";
import { DefenseLDiversityChart } from "./DefenseLDiversityChart";
import { DefensePaddingChart } from "./DefensePaddingChart";
import { DefenseRequestObfuscationChart } from "./DefenseRequestObfuscationChart";
import { DilithiumChart } from "./DilithiumChart";
import { DpCompareChart } from "./DpCompareChart";
import { EconomyChart } from "./EconomyChart";
import { EventBusChart } from "./EventBusChart";
import { EventGraphChart } from "./EventGraphChart";
import { FederatedStatusChart } from "./FederatedStatusChart";
import { FROSTChart } from "./FROSTChart";
import { GATAttentionChart } from "./GATAttentionChart";
import { GarchChart } from "./GarchChart";
import { GrangerMatrix } from "./GrangerMatrix";
import { InflationChart } from "./InflationChart";
import { KyberKEMChart } from "./KyberKEMChart";
import { LineChart } from "./LineChart";
import { LogisticsCapacityChart } from "./LogisticsCapacityChart";
import { LogisticsDispatchChart } from "./LogisticsDispatchChart";
import { LogisticsEchelonChart } from "./LogisticsEchelonChart";
import { LogisticsFillRateChart } from "./LogisticsFillRateChart";
import { LogisticsInventoryHealthChart } from "./LogisticsInventoryHealthChart";
import { LogisticsOrdersChart } from "./LogisticsOrdersChart";
import { LogisticsReorderPolicyChart } from "./LogisticsReorderPolicyChart";
import { LogisticsVRPChart } from "./LogisticsVRPChart";
import { LogitChart } from "./LogitChart";
import { MempoolChart } from "./MempoolChart";
import { MixNetChart } from "./MixNetChart";
import { MonteCarloFan } from "./MonteCarloFan";
import { MultiCheckpointChart } from "./MultiCheckpointChart";
import { MultiplierZKChart } from "./MultiplierZKChart";
import { OperatorScenarioChart } from "./OperatorScenarioChart";
import { PCAScree } from "./PCAScree";
import { PedersenChart } from "./PedersenChart";
import { PermutationChart } from "./PermutationChart";
import { PolicyInspector } from "./PolicyInspector";
import { PSIChart } from "./PSIChart";
import { RegressionChart } from "./RegressionChart";
import { RewardShapingChart } from "./RewardShapingChart";
import { ROCChart } from "./ROCChart";
import { SaliencyChart } from "./SaliencyChart";
import { SchnorrChart } from "./SchnorrChart";
import { ShamirChart } from "./ShamirChart";
import { SlashingChart } from "./SlashingChart";
import { SnarkForgeChart } from "./SnarkForgeChart";
import { SPHINCSChart } from "./SPHINCSChart";
import { SpectralChart } from "./SpectralChart";
import { STARKChart } from "./STARKChart";
import { StoryModeChart } from "./StoryModeChart";
import { SurvivalChart } from "./SurvivalChart";
import { TFHEChart } from "./TFHEChart";
import { ThresholdECDSAChart } from "./ThresholdECDSAChart";
import { TopicsBar } from "./TopicsBar";
import { TrainingCurves } from "./TrainingCurves";
import { ValueMapChart } from "./ValueMapChart";
import { VarIrfChart } from "./VarIrfChart";
import { VDFChart } from "./VDFChart";
import { VerkleChart } from "./VerkleChart";
import { VRFLeaderChart } from "./VRFLeaderChart";
import { WealthChart } from "./WealthChart";
import { WorldBranchChart } from "./WorldBranchChart";
import { WorldSnapshotChart } from "./WorldSnapshotChart";
import { YaoChart } from "./YaoChart";
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
  | "stark"
  | "frost"
  | "sphincs"
  | "verkle"
  | "bbs_plus"
  | "threshold_ecdsa"
  | "yao"
  | "psi"
  | "mix_net"
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
  | "attack_agent_fingerprint"
  | "attack_trajectory_fingerprint"
  | "attack_membership_inference"
  | "attack_model_inversion"
  | "attack_reward_poisoning"
  | "attack_cache_sidechannel"
  | "operator_scenarios"
  | "custom_policy"
  | "ctf"
  | "story_mode"
  | "world_branches";

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

type MetricMeta = {
  label: string;
  description: string;
  yUnit?: string;
  cli?: string;
};

const META: Record<MetricKind, MetricMeta> = {
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
    cli: "pno enable && pno query-dp money_supply 0.05",
  },
  signing_verified: {
    label: "Dilithium signatures verified",
    description:
      "cumulative count of per-tick ML-DSA-65 signature verifications across all agents. Grows linearly; rejected count tracked separately.",
    cli: "pna replay-cmd",
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
    cli: "pno enable && pno buy 0 3",
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
    cli: "psh lesson processes",
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
    cli: "pna dp-reconstruct --bits 64 --queries 400 --noise 0.1",
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
    cli: "pna byzantine-cmd --submit-self-slash",
  },
  training_curves: {
    label: "Live MAPPO training — start/stop + curves",
    description:
      "Click START and a background asyncio task begins running PPO updates against the SAME actor that drives the live arena. Each iteration: rollout 64 steps in an internal env, compute GAE advantages, run 4 PPO epochs, append (actor_loss, critic_loss, entropy, KL, mean_reward) to the curves below. The live policy mutates in real time.",
    cli: "curl -X POST http://localhost:8000/learning/training/start && curl -s http://localhost:8000/learning/training/curves | jq",
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
  gat_attention: {
    label: "GATv2 — graph attention weights",
    description:
      "GATv2 pathfinder over the live arena. Pick any source node; the bars show how much that node attends to each of its in-graph neighbours under the layer-1 softmax. Weights are RANDOM (no trained checkpoint shipped for the pathfinder) so the panel is teaching the architecture, not a learned policy. Toggle L1/L2 to see two-hop attention.",
  },
  saliency: {
    label: "Saliency — which features drive the policy",
    description:
      "For the chosen agent, compute ∂p(chosen_action)/∂x_i via autograd through the actor. Bigger bars = features the policy is currently most sensitive to. Useful for sanity-checking what the network is using: if 'is_goal' bars dominate, the agent is goal-oriented; if 'cost' bars dominate, it's avoiding expensive moves.",
  },
  ckks_compare: {
    label: "CKKS — encrypt → decrypt round-trip",
    description:
      "CKKS is APPROXIMATE homomorphic encryption. We encrypt a known plaintext, decrypt, and show plaintext vs decrypted side by side plus the absolute error per slot. The ciphertext preview is hex of the first 32 bytes — the full thing is kilobytes, opaque, and only the secret-key holder can decrypt it.",
    cli: "psh lesson crypto_tools",
  },
  kyber_kem: {
    label: "Kyber (ML-KEM-768) — post-quantum KEM",
    description:
      "Generate fresh keypair, encapsulate a shared secret against the public key, decapsulate with the secret key, check they match. Then flip one byte of the ciphertext and observe IMPLICIT REJECTION — Kyber returns a deterministic-but-different shared secret rather than raising, so callers MUST authenticate the transcript before trusting the secret.",
  },
  multi_checkpoint: {
    label: "Multi-checkpoint A/B compare",
    description:
      "Load a second MAPPO checkpoint into a side slot, then both policies are evaluated on the same live observations. KL divergence + top-action agreement quantify how different the two are. A common workflow: train two seeds, load both, see whether they agree on dominant actions despite different reward trajectories.",
  },
  vdf: {
    label: "Wesolowski VDF — compute vs verify",
    description:
      "Verifiable Delay Function. The Eval phase is INHERENTLY SEQUENTIAL — T modular squarings, no parallel speedup possible. The verify phase is fast (one modular exponentiation per side of the equation π^prime · x^r ≡ y mod p). The compute/verify RATIO is what makes VDFs useful as wall-clock-time tokens for unbiasable randomness (no proposer can pre-compute the result significantly ahead of time).",
    cli: "curl -s http://localhost:8000/vdf | jq",
  },
  dilithium: {
    label: "Dilithium — agent signature inspector",
    description:
      "Every agent in Penumbra signs its moves with ML-DSA-65 (Dilithium-3). Pick any agent → see its public key, sign a sample message, verify honest+tampered. Post-quantum guarantee comes from Module-LWE + Module-SIS hardness — resists Shor.",
    cli: "pno sign deadbeef && pno verify <msg> <sig> <pk>",
  },
  shamir: {
    label: "Shamir secret sharing (n, t)",
    description:
      "A secret S becomes N shares such that ANY T of them recover S exactly, but T-1 shares recover NOTHING (information-theoretic, not computational). Verified live: t-of-n reconstruction matches; (t-1)-of-n returns garbage. Adjust n and t to see the polynomial change degree.",
  },
  tfhe: {
    label: "Educational TFHE (LWE) bit gates",
    description:
      "LWE encrypts one bit per ciphertext (a, b) where b = ⟨a, s⟩ + scale·bit + noise. Homomorphic NOT and XOR are just arithmetic on the ciphertext components. Decryption round-trip + gate correctness verified live. Production TFHE adds bootstrapping to reset the noise after each gate.",
  },
  world_snapshot: {
    label: "World snapshots — save/load full state",
    description:
      "Capture the full perpetual simulation state (chain head, agent positions + policies, encrypted heatmap state, market wallets, RNG cursor) under a name. Load any snapshot to roll back. This is the persistence layer that makes the perpetual loop debuggable — you can experiment, branch, restore.",
    cli: "pna world save my-snap && pna world list && pna world load my-snap",
  },
  arena_graph: {
    label: "Arena graph — force-directed view",
    description:
      "The same nodes + edges + goals you see on the world map, laid out with a Fruchterman-Reingold relaxation so the connectivity STRUCTURE is visible (clusters, bottlenecks, isolated subgraphs). Ember = goals, edge thickness ∝ cost. Recomputed every 6s as topology mutates.",
  },
  pedersen: {
    label: "Pedersen commitments + homomorphic add",
    description:
      "C(m, r) = g^m · h^r mod p. Hiding (random h^r masks m); binding (changing m without breaking discrete log is infeasible). Additively homomorphic — multiplying ciphertexts gives a commitment to the sum. Verify shows honest ACCEPT, tampered REJECT, and the C(a)·C(b) = C(a+b) check.",
  },
  beaver: {
    label: "Beaver triples — secret multiplication",
    description:
      "N parties each hold an additive share of x and y plus a Beaver triple (a, b, c=a·b). Local arithmetic + ONE round of broadcast computes additive shares of x·y. None of the parties learn x or y. Σ z_i mod p reconstructs x·y exactly.",
  },
  schnorr: {
    label: "Schnorr Σ-protocol (Fiat-Shamir)",
    description:
      "Prover knows witness x s.t. y = g^x. Publishes (t, c, s) where c = H(y || t || context). Verifier recomputes c and checks g^s ≡ t · y^c. Honest accepts; wrong context rejects (challenge mismatch); tampered s rejects (pairing fails).",
  },
  zk_multiplier: {
    label: "Groth16 — multiplier circuit",
    description:
      "The simplest non-trivial circom circuit: a * b === c. The shipped proof has c = 15 (e.g. a=3, b=5). Honest verifies; bumping c to 16 rejects because the proof binds to the public input. Same py_ecc verifier as the legal-path circuit, just a different VK/proof pair.",
  },
  snark_forge: {
    label: "SNARK forgery — verifier rejects",
    description:
      "Attempt to fool the Groth16 verifier WITHOUT a witness. Two attacks: (1) flip A's low bit — the proof point goes off-curve, pairing equation fails. (2) Replay an honest proof with TAMPERED public inputs — Groth16 binds proofs to public inputs via the linear-combination IC, so verifier rejects. The honest control still accepts.",
    cli: "pna snark-forge",
  },
  stark: {
    label: "STARK — transparent FRI verifier",
    description:
      "Educational FRI-STARK: Reed-Solomon codeword over an NTT-friendly subgroup, Merkle-pinned commitments, log|D| folding rounds under Fiat-Shamir challenges. NO trusted setup (in contrast to Groth16). Verifier rejects evaluation tampering (folding consistency fails) and Merkle-root tampering (auth-path mismatch). Soundness rests on FRI low-degree, Merkle binding (SHA-256 collision-resistance), and ROM Fiat-Shamir. Production STARKs (Cairo, Plonky3, RISC Zero) ship the same verifier shape with ~80 queries to push soundness error below 2^-100.",
  },
  frost: {
    label: "FROST — threshold Schnorr (round-optimised)",
    description:
      "t-of-n participants co-sign a Schnorr signature that verifies as plain (R, s) — the threshold structure is INVISIBLE to the verifier. Per-signature binding factors ρᵢ defeat the Drijvers-style sub-exponential forgery on naive 2-round protocols. Used by Bitcoin Lightning, Coinbase MPC custody, Frostsnap.",
  },
  sphincs: {
    label: "SPHINCS+ vs Dilithium — PQ signature sizes",
    description:
      "Hash-based PQ signatures (SPHINCS+-128f-simple, NIST FIPS 205) trade signature size (~17 KB) for structural simplicity: only hash-collision resistance is assumed. ML-DSA-65 (Dilithium-3) ships smaller ~3.3 KB sigs but rests on Module-LWE. Two PQ families on one shelf gives Penumbra two independent migration paths.",
  },
  verkle: {
    label: "Verkle tree — KZG opening + Merkle size comparison",
    description:
      "Verkle proofs replace each Merkle sibling list (depth × 32 B) with ONE KZG opening per level (48 B G1 point). At 1M leaves the compression is ~4×; at 256-ary trees of state-size depth it climbs into 10–20×. Ethereum's 'Verge' roadmap adopts Verkle precisely for stateless-client proof bandwidth.",
  },
  bbs_plus: {
    label: "BBS+ — selective-disclosure credentials",
    description:
      "Issuer signs ONCE over an L-attribute vector; holder later proves 'I have a valid credential whose attributes at indices I are values V' without revealing the rest. Pairing equation e(A, w + g₂·e) = e(g₁ + h₀·s + Σ hᵢ·mᵢ, g₂). Powers EU Digital Identity Wallet 2026 + AnonCreds.",
  },
  threshold_ecdsa: {
    label: "Threshold ECDSA — GG18 (educational)",
    description:
      "n-of-n parties co-sign a secp256k1 ECDSA signature. The hard step is k⁻¹·d under secret sharing — GG18 solves it with Paillier-MtA + ZK proofs; our educational variant uses a trusted dealer + Beaver-style additive shares of (k⁻¹·d). The signature is plain ECDSA on the wire.",
  },
  yao: {
    label: "Yao's millionaires — garbled-circuit comparator",
    description:
      "Two parties learn ONLY whether a < b, a == b, or a > b — never the values. Each wire carries 2 random 128-bit labels; each gate ships 4 doubly-encrypted output labels; the evaluator decrypts EXACTLY ONE row per gate using OT-selected input labels. The output label decodes to {0, 1}.",
  },
  psi: {
    label: "Private Set Intersection — OPRF/DH",
    description:
      "Alice + Bob find S_A ∩ S_B without revealing anything else. Alice ships {H(x)^α}; Bob raises by his secret β and publishes {H(y)^β}; Alice removes α and compares OPRF images. Used by Apple PSI, Google Password Checkup, Signal contact discovery.",
  },
  mix_net: {
    label: "Mix-net — Loopix-style onion routing",
    description:
      "onion_i = E_{K_i}(next_hop || delay || onion_{i+1}). Each relay peels one layer, learns predecessor + successor only. A global adversary cannot link sender → receiver as long as one honest relay shuffles its queue. The Penumbra dispatcher hides assignment metadata this way.",
  },
  logistics_fill_rate: {
    label: "Logistics — end-customer fill rate",
    description:
      "Demand on the cities is satisfied or backlogged. served / requested is the fill rate; backlog accumulates whenever inventory runs out. The per-product strip exposes which goods underserve relative to others.",
  },
  logistics_inventory_health: {
    label: "Logistics — inventory health",
    description:
      "Per-(city, product) stock vs cap, with stockout count + holding/stockout cost totals. Stockouts are red; lowest-stock cells lead the list.",
  },
  logistics_orders: {
    label: "Logistics — order book",
    description:
      "Pending + fulfilled orders in the LogisticsMempool. Lead-time stats (median / p95) measure how long an (s,S)-triggered order sits before its carrier closes it out.",
  },
  logistics_reorder_policy: {
    label: "Logistics — (s, S) reorder policy",
    description:
      "When inventory + outstanding < s, place an order up to S. Tweak the fractions to see the order book and stockout count respond. Lead time is fixed in Tier 1.",
  },
  logistics_capacity: {
    label: "Logistics — cargo utilisation",
    description:
      "Per-agent carried-units / cap. The BUY path is capped by remaining capacity, so a saturated fleet starts refusing inventory until it sells.",
  },
  logistics_vrp: {
    label: "Logistics — VRP optimisation baseline",
    description:
      "Snapshot capacitated VRP solver (greedy → 2-opt, optional OR-Tools) over the live mempool. The cost gap vs the naive fulfilment baseline shows how much an omniscient central planner could save over the live decentralised policy.",
  },
  logistics_echelon: {
    label: "Logistics — multi-echelon supply chain (Tier 3)",
    description:
      "Suppliers produce raw goods → distributors hold buffer stock → cities face end-customer demand. Each tier reorders from its upstream neighbour with a deterministic lead time. The bullwhip ratio (variance of orders / variance of demand) measures Forrester's classic upstream amplification effect.",
  },
  logistics_dispatch: {
    label: "Logistics — carrier dispatch",
    description:
      "Greedy nearest-agent assignment + agent-driven fulfilment. Each order is bound to one carrier; the order settles when that agent reaches the destination city carrying the requested product (city inventory ++, agent inventory --, agent.coins += reward). Stale assignments are released after 3x lead time; orders waiting more than 5x lead time fall back to a phantom carrier (id = -1) so the simulation never deadlocks.",
    cli: "pno enable && pno dispatch 5 0 4 1.5",
  },
  federated_status: {
    label: "Federated learning — status & controls",
    description:
      "FedAvg (Tier 1) and CKKS-encrypted aggregation (Tier 2) over per-agent local SGD deltas. Optional DP-SGD clip + Gaussian noise (Tier 3). Krum / TrimmedMean Byzantine-robust aggregators are also shipped as functions.",
    cli: "curl -s http://localhost:8000/learning/federated/status | jq",
  },
  event_bus: {
    label: "Event bus — cross-pillar signals",
    description:
      "Phase 6a: in-process pub-sub. Analytics consumers (GARCH, CPI, Gini) emit signals; logistics + market handlers react (ReorderPolicy retune, Market.pricing_regime). Per-kind p99 handler latency is tracked here so regressions surface immediately.",
  },
  event_graph: {
    label: "Event graph — producer/consumer wiring",
    description:
      "Phase 6a Tier 5 cross-pillar observability. Each event kind seen in the recent window is rendered as a node with its emit count on the left and the matching handler call count + p99 latency on the right. Chain block.finalised → Market.credit_block_winners and chain.validator.slashed → FederatedTrainer.block_agent are the new Tier 5 edges.",
  },
  security_blocked: {
    label: "Security — blocked agents",
    description:
      "Phase 6a Tier 2: agents whose signing rejections crossed the threshold are auto-blocked from Market trades, logistics dispatch, and FL aggregation. The block lifts after the cool-off window. The history counter never decreases; the gated-trade gauge counts every BUY/SELL skipped because of an active block.",
  },
  defense_data_poisoning: {
    label: "Defense — decoy injection (privacy-utility curve)",
    description:
      "Phase 5 Tier 3: defender mixes a configurable fraction of plausible decoy records into a release so an attacker that trusts every record fits a contaminated distribution. Decoys are sampled per-field from the empirical distribution of the real records and flagged with is_decoy=True for defender-side filters. Curve sweeps rate vs (attacker_max_accuracy = 1 − rate, utility shift of mean + std).",
  },
  defense_padding: {
    label: "Defense — request padding + Poisson cover traffic",
    description:
      "Phase 5 Tier 3: pad every message to a fixed bucket so packet sizes collapse to one visible size, and emit cover traffic on a Poisson schedule so inter-arrival timing leaks nothing. Bandwidth overhead = target_size / mean(real size); privacy headline is the distinct-sizes-after count collapsing to 1. Poisson arrivals are the requirement Loopix relies on for its mix-net bound.",
  },
  defense_k_anonymity: {
    label: "Defense — k-anonymity (suppression)",
    description:
      "Phase 5 Tier 3: release only those records whose quasi-identifier tuple is shared by at least k − 1 others; everything else is suppressed. Adversary best re-identification on any released bucket is bounded by 1/k. Curve sweeps k vs (suppression rate, 1/k). Vulnerable to the homogeneity attack when sensitive values are shared inside a bucket — see the ℓ-diversity tile.",
  },
  defense_l_diversity: {
    label: "Defense — ℓ-diversity (k-anonymity + distinctness)",
    description:
      "Phase 5 Tier 3: tightens k-anonymity by requiring each released bucket to contain ≥ ℓ distinct values on the sensitive column. Defeats the homogeneity attack at the cost of more aggressive suppression. The curve fixes k and sweeps ℓ; cyan dots mark homogeneity-safe releases. The next upgrade — t-closeness — defends against the skewness attack.",
  },
  defense_gan: {
    label: "Defense — synthetic-trace release (Gaussian stub)",
    description:
      "Phase 5 Tier 3: release samples from a generative model fitted to the real trajectory features instead of the records themselves. Every released sample is a fresh draw, so a membership-inference adversary on the output scores at chance. The Tier 3 stub uses a Gaussian fit (mean + covariance) with a tunable correlation-preserve knob; CycleGAN / TimeGAN deferred behind the same API.",
  },
  defense_request_obfuscation: {
    label: "Defense — Bonferroni + dummy DP queries",
    description:
      "Phase 5 Tier 3: split the family-wise ε across all queries (per-query ε = ε_family / k) and inject k_dummy decoy queries so the adversary's family grows. An attacker that wants to maintain its usual family-wise guarantee must accept a smaller per-query budget — its DP accountant drains proportionally faster. Curve sweeps dummy count vs attacker budget inflation.",
  },
  attack_agent_fingerprint: {
    label: "Attack — 1-NN agent fingerprint",
    description:
      "Phase 5 Tier 2: build a per-agent feature vector from action histogram, latency stats, trajectory curvature and trade pattern; a 1-NN classifier re-identifies agents across matches well above the 1/N baseline. Defence is DP noise on aggregates + per-match identity shuffling.",
    cli: "pna linkability-cmd --agents 5 --matches 30",
  },
  attack_trajectory_fingerprint: {
    label: "Attack — HMM trajectory fingerprint",
    description:
      "Phase 5 Tier 2: fit one Baum-Welch HMM per agent over historical action sequences. Forward log-likelihood scoring re-identifies unseen trajectories by picking the most likely model. Captures temporal structure that 1-NN over static features misses. Defence: RAPPOR-style action randomisation.",
    cli: "pna linkability-cmd --agents 8 --matches 50",
  },
  attack_membership_inference: {
    label: "Attack — Shokri shadow-model MI",
    description:
      "Phase 5 Tier 2: Shokri et al. 2017 trains N small shadow classifiers; their confidence vectors on members vs non-members teach a meta-classifier (ridge logistic) that decides 'this observation was in the training set' on the real target policy. Defence: DP-SGD + output confidence clipping drops advantage below 1%.",
  },
  attack_model_inversion: {
    label: "Attack — Deep Leakage from Gradients",
    description:
      "Phase 5 Tier 2: Zhu et al. 2019. Given a leaked per-sample gradient (think: a federated round delta on a single example), recover the input by minimising ‖∇_θ L(model(x̂), y) − ∇_observed‖² over x̂. Defence: DP-SGD per-sample gradient clipping + Gaussian noise + CKKS secure aggregation hides individual gradients.",
  },
  attack_reward_poisoning: {
    label: "Attack — reward poisoning (5% backdoor)",
    description:
      "Phase 5 Tier 2: inject inflated rewards on 5% of training episodes, all tied to the attacker's target action. Softmax REINFORCE on a 4-armed bandit drifts toward the attacker's preference and away from the true best action. Defence: reward clipping, median-of-means aggregation, Byzantine-robust aggregators (Krum, TrimmedMean).",
  },
  attack_cache_sidechannel: {
    label: "Attack — cache side-channel on CKKS (must FAIL)",
    description:
      "Phase 5 Tier 2 pedagogical: Flush+Reload-style timing on TenSEAL CKKS add over sparse vs dense ciphertexts; Welch t-test the latencies. Modern CKKS pads to the full polynomial degree on every op, so the t-stat stays small and `leak_detected` returns False. The companion sanity test (artificially leaky op) confirms the attack DOES detect leaks when present.",
    cli: "pna timing --samples 50",
  },
  operator_scenarios: {
    label: "Operator — scenario engine (12 starter drills)",
    description:
      "Phase 6b Tier 5: pick one of 12 starter scenarios (defense, attack, chain, FL, logistics, sandbox) and the runner snapshots the operator's start state then evaluates victory + failure clauses against live state — at 1 Hz while the Operator panel is open, and at every action via the save-resume hook so a closed tab can be reopened (or the server restarted) and the session resumes from the saved sim-tick. Each scenario declares its preconditions, opening event, and per-axis scorecard weights so the composite is comparable across runs.",
    cli: "pno enable && pno status",
  },
  custom_policy: {
    label: "Custom Agent Policy — sandboxed injection",
    description:
      "Phase 5 Tier 4: write a Python `policy(state, observation)` function, the backend AST-validates and runs it in a numpy+math-only sandbox with a 50 ms wall-clock budget. Use it to test attack policies (adversarial, byzantine, reward-poisoning) against the live arena without rebuilding the server.",
    cli: 'curl -X POST http://localhost:8000/attacker/policy -d \'{"name":"x","code":"def policy(s,o): return 0","scope":"all"}\'',
  },
  ctf: {
    label: "Capture-the-Flag — privacy + crypto challenges",
    description:
      "Phase 5 Tier 4: 5 starter YAML challenges (DP reconstruction, linkability, replay, byzantine equivocation, SNARK forge). Pick a challenge, read its setup + acceptance criteria, build the attack offline, submit the flag for a per-challenge leaderboard slot.",
    cli: "curl -s http://localhost:8000/ctf/challenges | jq",
  },
  story_mode: {
    label: "Story Mode — cross-pillar attack chains",
    description:
      "Phase 5 Tier 5: 8 narrative `psh lesson` tutorials that thread an attack across logistics, statistics, NN, RL, and crypto pillars. Filter by difficulty or pillar; pick a story to copy the launch command for the embedded terminal.",
    cli: "psh lessons && psh lesson story_bullwhip_leak",
  },
  world_branches: {
    label: "World branches — pickle-clone & compare",
    description:
      "Phase 5 Tier 4: snapshot the live simulation into N in-memory branches via pickle round-trip. Advance any branch independently for K ticks and compare positions + wealth + tick counter side-by-side. Branches are intentionally non-persistent — process-local what-if explorations.",
    cli: "pna world save baseline && pna world load baseline",
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
  const dialogRef = useRef<HTMLDivElement | null>(null);
  useFocusTrap(dialogRef, open && metric !== null);

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
    if (metric === "gat_attention") {
      return <GATAttentionChart />;
    }
    if (metric === "saliency") {
      return <SaliencyChart />;
    }
    if (metric === "ckks_compare") {
      return <CKKSCompareChart />;
    }
    if (metric === "kyber_kem") {
      return <KyberKEMChart />;
    }
    if (metric === "multi_checkpoint") {
      return <MultiCheckpointChart />;
    }
    if (metric === "vdf") {
      return <VDFChart />;
    }
    if (metric === "dilithium") {
      return <DilithiumChart />;
    }
    if (metric === "shamir") {
      return <ShamirChart />;
    }
    if (metric === "tfhe") {
      return <TFHEChart />;
    }
    if (metric === "world_snapshot") {
      return <WorldSnapshotChart />;
    }
    if (metric === "arena_graph") {
      return <ArenaGraphChart />;
    }
    if (metric === "pedersen") {
      return <PedersenChart />;
    }
    if (metric === "beaver") {
      return <BeaverChart />;
    }
    if (metric === "schnorr") {
      return <SchnorrChart />;
    }
    if (metric === "zk_multiplier") {
      return <MultiplierZKChart />;
    }
    if (metric === "snark_forge") {
      return <SnarkForgeChart />;
    }
    if (metric === "stark") {
      return <STARKChart />;
    }
    if (metric === "frost") {
      return <FROSTChart />;
    }
    if (metric === "sphincs") {
      return <SPHINCSChart />;
    }
    if (metric === "verkle") {
      return <VerkleChart />;
    }
    if (metric === "bbs_plus") {
      return <BBSPlusChart />;
    }
    if (metric === "threshold_ecdsa") {
      return <ThresholdECDSAChart />;
    }
    if (metric === "yao") {
      return <YaoChart />;
    }
    if (metric === "psi") {
      return <PSIChart />;
    }
    if (metric === "mix_net") {
      return <MixNetChart />;
    }
    if (metric === "logistics_fill_rate") {
      return <LogisticsFillRateChart />;
    }
    if (metric === "logistics_inventory_health") {
      return <LogisticsInventoryHealthChart />;
    }
    if (metric === "logistics_orders") {
      return <LogisticsOrdersChart />;
    }
    if (metric === "logistics_reorder_policy") {
      return <LogisticsReorderPolicyChart />;
    }
    if (metric === "logistics_capacity") {
      return <LogisticsCapacityChart />;
    }
    if (metric === "logistics_vrp") {
      return <LogisticsVRPChart />;
    }
    if (metric === "logistics_echelon") {
      return <LogisticsEchelonChart />;
    }
    if (metric === "logistics_dispatch") {
      return <LogisticsDispatchChart />;
    }
    if (metric === "federated_status") {
      return <FederatedStatusChart />;
    }
    if (metric === "event_bus") {
      return <EventBusChart />;
    }
    if (metric === "event_graph") {
      return <EventGraphChart />;
    }
    if (metric === "security_blocked") {
      return <BlockedAgentsChart />;
    }
    if (metric === "defense_data_poisoning") {
      return <DefenseDataPoisoningChart />;
    }
    if (metric === "defense_padding") {
      return <DefensePaddingChart />;
    }
    if (metric === "defense_k_anonymity") {
      return <DefenseKAnonymityChart />;
    }
    if (metric === "defense_l_diversity") {
      return <DefenseLDiversityChart />;
    }
    if (metric === "defense_gan") {
      return <DefenseGANChart />;
    }
    if (metric === "defense_request_obfuscation") {
      return <DefenseRequestObfuscationChart />;
    }
    if (metric === "attack_agent_fingerprint") {
      return <AttackAgentFingerprintChart />;
    }
    if (metric === "attack_trajectory_fingerprint") {
      return <AttackTrajectoryFingerprintChart />;
    }
    if (metric === "attack_membership_inference") {
      return <AttackMembershipInferenceChart />;
    }
    if (metric === "attack_model_inversion") {
      return <AttackModelInversionChart />;
    }
    if (metric === "attack_reward_poisoning") {
      return <AttackRewardPoisoningChart />;
    }
    if (metric === "attack_cache_sidechannel") {
      return <AttackCacheSidechannelChart />;
    }
    if (metric === "operator_scenarios") {
      return <OperatorScenarioChart />;
    }
    if (metric === "custom_policy") {
      return <CustomPolicyChart />;
    }
    if (metric === "ctf") {
      return <CTFChart />;
    }
    if (metric === "story_mode") {
      return <StoryModeChart />;
    }
    if (metric === "world_branches") {
      return <WorldBranchChart />;
    }
    return <LineChart values={values ?? []} label={meta.label} yUnit={meta.yUnit} />;
  })();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6">
      {/* Backdrop: clickable to dismiss, but hidden from screen readers so the */}
      {/* dialog content is announced first; the explicit "Close" button is the */}
      {/* SR-discoverable dismiss. Esc also dismisses via the effect above. */}
      <div
        aria-hidden="true"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-transparent"
      />
      <div
        ref={dialogRef}
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
            aria-label="Close"
            onClick={onClose}
            className="text-[14px] leading-none text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-text)]"
          >
            {"×"}
          </button>
        </div>
        <p className="mb-4 text-[11px] leading-relaxed text-[color:var(--color-penumbra-muted)]">
          {meta.description}
        </p>
        {meta.cli && (
          <div className="mb-4 border-l-2 border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-bg)] px-3 py-2">
            <div className="mb-1 text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-muted)]">
              try it in your shell
            </div>
            <code className="block whitespace-pre-wrap break-all font-mono text-[11px] text-[color:var(--color-penumbra-cyan)]">
              {meta.cli}
            </code>
          </div>
        )}
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
