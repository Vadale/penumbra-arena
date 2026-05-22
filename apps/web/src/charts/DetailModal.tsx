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
  ArimaForecast as ArimaForecastData,
  BayesianPosterior as BayesianPosteriorData,
  ClusterScatter as ClusterScatterData,
  EconomySnapshot as EconomySnapshotData,
  GrangerMatrix as GrangerMatrixData,
  LogitResult as LogitResultData,
  MonteCarloFan as MCFanData,
  PCAResult,
  RegressionFit,
} from "../streams/dashboard";
import { ArimaChart } from "./ArimaChart";
import { BayesianDensity } from "./BayesianDensity";
import { ClusterScatter } from "./ClusterScatter";
import { EconomyChart } from "./EconomyChart";
import { GrangerMatrix } from "./GrangerMatrix";
import { LineChart } from "./LineChart";
import { LogitChart } from "./LogitChart";
import { MonteCarloFan } from "./MonteCarloFan";
import { PCAScree } from "./PCAScree";
import { RegressionChart } from "./RegressionChart";
import { TopicsBar } from "./TopicsBar";

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
  | "economy";

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
      return <RegressionChart fit={regression} />;
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
