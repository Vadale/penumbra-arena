/**
 * Per-metric chart routing for DetailModal.
 *
 * Extracted from DetailModal.tsx so the modal shell stays focused
 * on dialog/keyboard/focus logic; this file owns the 100+ chart
 * imports and the metric → component switch.
 *
 * Per-metric chart routing (representative samples):
 *   trajectory_mean  → RegressionChart (OLS + R² + 95% band)
 *   hdbscan_clusters → ClusterScatter (PC1/PC2 with HDBSCAN labels)
 *   var95            → MonteCarloFan (bootstrap percentile band + VaR/CVaR)
 *   pca              → PCAScree (eigenvalues + cumulative variance)
 *   topics           → TopicsBar
 *   everything else  → LineChart (generic time-series)
 */

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
import { AchievementsPanel } from "./AchievementsPanel";
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
import { BranchCompareChart } from "./BranchCompareChart";
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
import type { MetricKind, MetricMeta } from "./DetailModalMeta";
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
import { LabPanel } from "./LabPanel";
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
import { NotificationSettings } from "./NotificationSettings";
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

export interface MetricBodyProps {
  metric: MetricKind;
  meta: MetricMeta;
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

export function MetricBody(props: MetricBodyProps) {
  const {
    metric,
    meta,
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
  } = props;

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
  if (metric === "lab_experiments") {
    return <LabPanel />;
  }
  if (metric === "branch_compare") {
    return <BranchCompareChart />;
  }
  if (metric === "notifications") {
    return <NotificationSettings />;
  }
  if (metric === "achievements") {
    return <AchievementsPanel />;
  }
  return <LineChart values={values ?? []} label={meta.label} yUnit={meta.yUnit} />;
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
