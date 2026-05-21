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
}

const POLL_MS = 500;

export function useDashboardSnapshot(): DashboardSnapshot | null {
  const [snap, setSnap] = useState<DashboardSnapshot | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch("/dashboard");
        if (!res.ok) return;
        const payload = (await res.json()) as DashboardSnapshot;
        if (!cancelled) setSnap(payload);
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

  return snap;
}
