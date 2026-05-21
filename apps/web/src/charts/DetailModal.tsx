/**
 * Modal that pops up when the user clicks an AnalyticsPanel cell.
 *
 * Renders the full-size chart appropriate for the metric: a generic
 * time-series line chart for scalar metrics, a bar chart for topics,
 * or a panel that says "no detail view yet" for everything else.
 *
 * Dismiss via Escape, backdrop click, or the explicit close button.
 */

import { useEffect } from "react";
import { LineChart } from "./LineChart";
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
  | "topics";

interface Props {
  open: boolean;
  onClose: () => void;
  metric: MetricKind | null;
  values?: number[];
  topicSizes?: Record<string, number>;
  topicTopWords?: Record<string, string[]>;
}

const META: Record<MetricKind, { label: string; description: string; yUnit?: string }> = {
  trajectory_mean: {
    label: "trajectory mean",
    description:
      "average L₂ norm of agent positions across the rolling window. Steady values mean the swarm is occupying a stable region; rising values mean it's spreading or migrating.",
  },
  trajectory_std: {
    label: "trajectory std",
    description: "standard deviation of the same trajectory series; a measure of swarm dispersion.",
  },
  hdbscan_clusters: {
    label: "HDBSCAN clusters",
    description:
      "density-based clustering on recent agent positions. Counts how many distinct factions the algorithm believes exist right now.",
  },
  arima_next: {
    label: "ARIMA(1,0,0) one-step forecast",
    description: "next-step prediction for the trajectory series under a simple AR(1) model.",
  },
  sinkhorn_cost: {
    label: "Sinkhorn / W₁ cost",
    description:
      "regularised optimal transport between successive encrypted-heatmap snapshots. Large = the density shifted between samples.",
  },
  var95: {
    label: "VaR 95%",
    description:
      "Value-at-Risk at the 95th percentile of the trajectory norm distribution. Empirical, no parametric assumption.",
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
    label: "Bayesian θ posterior mean",
    description:
      "posterior mean of θ under a Beta-Binomial model where 'success' = trajectory norm exceeds the rolling median.",
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
};

export function DetailModal({ open, onClose, metric, values, topicSizes, topicTopWords }: Props) {
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
          {metric === "topics" ? (
            <TopicsBar topicSizes={topicSizes ?? {}} topWords={topicTopWords ?? {}} />
          ) : (
            <LineChart values={values ?? []} label={meta.label} yUnit={meta.yUnit} />
          )}
        </div>
      </div>
    </div>
  );
}
