/**
 * Streaming analytics dashboard client.
 *
 * Polls /dashboard at 2 Hz and exposes the resulting snapshot for any
 * component that wants to render it.
 */

import { useEffect, useState } from "react";

export interface DashboardSummary {
  n: number;
  mean: number;
  std: number;
  median: number;
  iqr: number;
  ci95_low: number;
  ci95_high: number;
}

export interface DPBudget {
  epsilon_total: number;
  epsilon_spent: number;
  epsilon_remaining: number;
}

export interface SigningStats {
  verified: number;
  rejected: number;
  n_agents: number;
}

export interface RegressionFit {
  slope: number;
  intercept: number;
  r_squared: number;
  n: number;
  sigma: number;
  points: [number, number][];
}

export interface ClusterScatter {
  points: [number, number, number][]; // (x, y, label)
  n_clusters: number;
  n_noise: number;
}

export interface MonteCarloFan {
  percentiles: Record<string, number>;
  var: number;
  cvar: number;
  n_samples: number;
}

export interface PCAResult {
  eigenvalues: number[];
  explained_variance_ratio: number[];
  top2_loadings: [number, number][];
}

export interface ArimaForecast {
  history: number[];
  next_value: number;
  next_std: number;
}

export interface LogitResult {
  intercept: number;
  slope: number;
  curve: [number, number][];
  points: [number, number][];
  n: number;
  pseudo_r2: number;
}

export interface BayesianPosterior {
  alpha: number;
  beta: number;
  mean: number;
  std: number;
  credible_low: number;
  credible_high: number;
  curve: [number, number][];
}

export interface GrangerMatrix {
  series_names: string[];
  p_values: number[][];
  max_lag: number;
  n_obs: number;
}

export interface EconomySnapshot {
  total_purchases: number;
  total_revenue: number;
  category_counts: Record<string, number>;
  top_products: [string, number, number][];
  basket_histogram: [number, number][];
}

export interface SurvivalCurve {
  times: number[];
  survival: number[];
  confidence_low: number[];
  confidence_high: number[];
  n_events: number;
  n_censored: number;
  median_time: number | null;
}

export interface SpectralReport {
  eigenvalues: number[];
  fiedler_value: number;
  n_nodes: number;
  n_edges: number;
  fiedler_vector: number[];
}

export interface CausalEstimate {
  n_treated: number;
  n_control: number;
  ipw_ate: number;
  ipw_se: number;
  aipw_ate: number;
  aipw_se: number;
  propensity_treated: number[];
  propensity_control: number[];
}

export interface VARImpulseResponse {
  series_names: string[];
  horizon: number;
  lag_order: number;
  irf: number[][][]; // [step][shock_series][response_series]
}

export interface GarchResult {
  omega: number;
  alpha: number;
  beta: number;
  persistence: number;
  log_returns: number[];
  conditional_volatility: number[];
}

export interface ANOVAReport {
  f_statistic: number;
  p_value: number;
  df_between: number;
  df_within: number;
  grouping: string;
  group_names: string[];
  group_means: number[];
  group_se: number[];
  group_n: number[];
  grand_mean: number;
}

export interface AutocorrelationReport {
  n_obs: number;
  max_lag: number;
  acf: number[];
  pacf: number[];
  conf_band: number;
}

export interface ROCData {
  fpr: number[];
  tpr: number[];
  thresholds: number[];
  auc: number;
}

export interface CorrelationMatrix {
  series_names: string[];
  pearson: number[][];
  spearman: number[][];
  n_obs: number;
}

export interface PermutationReport {
  observed_ate: number;
  null_samples: number[];
  p_two_sided: number;
  n_permutations: number;
}

export interface CandleBar {
  bucket: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandleSeries {
  product_id: number;
  product_name: string;
  category: string;
  candles: CandleBar[];
  total_volume: number;
  bucket_ticks: number;
}

export interface InflationSeries {
  cpi: [number, number][]; // (tick, index)
  money_supply: [number, number][];
  n_samples: number;
}

export interface WealthReport {
  lorenz_x: number[];
  lorenz_y: number[];
  gini: number;
  p10: number;
  p50: number;
  p90: number;
  p99: number;
  total_wealth: number;
  n_agents: number;
}

export interface DashboardSnapshot {
  tick: number;
  summary: DashboardSummary | null;
  hdbscan_n_clusters: number | null;
  hdbscan_n_noise: number | null;
  arima_next: number | null;
  arima_std: number | null;
  changepoints: number[];
  sinkhorn_cost: number | null;
  h0_total: number | null;
  h1_total: number | null;
  h0_bars: [number, number][];
  h1_bars: [number, number][];
  bayesian_theta: number | null;
  var95: number | null;
  dp_budget: DPBudget | null;
  signing_stats: SigningStats;
  n_topics: number | null;
  topic_sizes: Record<string, number>;
  topic_top_words: Record<string, string[]>;
  regression: RegressionFit | null;
  cluster_scatter: ClusterScatter | null;
  monte_carlo: MonteCarloFan | null;
  pca: PCAResult | null;
  arima_forecast: ArimaForecast | null;
  logit: LogitResult | null;
  bayesian_posterior: BayesianPosterior | null;
  granger: GrangerMatrix | null;
  economy: EconomySnapshot | null;
  survival: SurvivalCurve | null;
  spectral: SpectralReport | null;
  causal: CausalEstimate | null;
  var_irf: VARImpulseResponse | null;
  garch: GarchResult | null;
  qq_points: [number, number][]; // Q-Q plot points (theoretical, sample) for OLS residuals.
  residual_vs_fitted: [number, number][];
  anova: ANOVAReport | null;
  autocorrelation: AutocorrelationReport | null;
  roc: ROCData | null;
  correlations: CorrelationMatrix | null;
  permutation: PermutationReport | null;
  candles: CandleSeries[];
  inflation: InflationSeries | null;
  wealth: WealthReport | null;
}

const POLL_MS = 500;
const HISTORY_CAPACITY = 60; // ~30 s of history at 500ms cadence

export interface DashboardHistory {
  trajectory_mean: number[];
  trajectory_std: number[];
  arima_next: number[];
  sinkhorn_cost: number[];
  var95: number[];
  bayesian_theta: number[];
  h0_total: number[];
  h1_total: number[];
  hdbscan_clusters: number[];
  dp_epsilon_spent: number[];
  signing_verified: number[];
  n_topics: number[];
}

const EMPTY_HISTORY: DashboardHistory = {
  trajectory_mean: [],
  trajectory_std: [],
  arima_next: [],
  sinkhorn_cost: [],
  var95: [],
  bayesian_theta: [],
  h0_total: [],
  h1_total: [],
  hdbscan_clusters: [],
  dp_epsilon_spent: [],
  signing_verified: [],
  n_topics: [],
};

function pushRolling(arr: number[], v: number | null): number[] {
  const next = [...arr, v ?? NaN];
  if (next.length > HISTORY_CAPACITY) next.shift();
  return next;
}

export interface DashboardLive {
  snap: DashboardSnapshot | null;
  history: DashboardHistory;
}

export function useDashboardLive(): DashboardLive {
  const [snap, setSnap] = useState<DashboardSnapshot | null>(null);
  const [history, setHistory] = useState<DashboardHistory>(EMPTY_HISTORY);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch("/dashboard");
        if (!res.ok) return;
        const payload = (await res.json()) as DashboardSnapshot;
        if (cancelled) return;
        setSnap(payload);
        setHistory((h) => ({
          trajectory_mean: pushRolling(h.trajectory_mean, payload.summary?.mean ?? null),
          trajectory_std: pushRolling(h.trajectory_std, payload.summary?.std ?? null),
          arima_next: pushRolling(h.arima_next, payload.arima_next),
          sinkhorn_cost: pushRolling(h.sinkhorn_cost, payload.sinkhorn_cost),
          var95: pushRolling(h.var95, payload.var95),
          bayesian_theta: pushRolling(h.bayesian_theta, payload.bayesian_theta),
          h0_total: pushRolling(h.h0_total, payload.h0_total),
          h1_total: pushRolling(h.h1_total, payload.h1_total),
          hdbscan_clusters: pushRolling(h.hdbscan_clusters, payload.hdbscan_n_clusters),
          dp_epsilon_spent: pushRolling(
            h.dp_epsilon_spent,
            payload.dp_budget?.epsilon_spent ?? null,
          ),
          signing_verified: pushRolling(
            h.signing_verified,
            payload.signing_stats?.verified ?? null,
          ),
          n_topics: pushRolling(h.n_topics, payload.n_topics),
        }));
      } catch {
        // ignore; next poll will retry
      }
    };
    void poll();
    const timer = window.setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return { snap, history };
}

/** Back-compat for older callers — returns just the snapshot. */
export function useDashboardSnapshot(): DashboardSnapshot | null {
  return useDashboardLive().snap;
}
