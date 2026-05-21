import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnalyticsPanel } from "./AnalyticsPanel";

describe("AnalyticsPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the connecting placeholder when /dashboard is silent", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise(() => {}) as never);
    render(<AnalyticsPanel />);
    expect(screen.getByText(/analytics connecting/i)).toBeInTheDocument();
  });

  it("renders the DP + signing tiles when the snapshot carries values", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          tick: 99,
          summary: null,
          hdbscan_n_clusters: null,
          hdbscan_n_noise: null,
          arima_next: null,
          arima_std: null,
          changepoints: [],
          sinkhorn_cost: null,
          h0_total: null,
          h1_total: null,
          h0_bars: [],
          h1_bars: [],
          bayesian_theta: null,
          var95: null,
          dp_budget: { epsilon_total: 5.0, epsilon_spent: 1.0, epsilon_remaining: 4.0 },
          signing_stats: { verified: 123, rejected: 0, n_agents: 50 },
          n_topics: 3,
          topic_sizes: { "0": 30, "1": 20, "2": 15 },
          topic_top_words: { "0": ["explore", "node", "topology"] },
        }),
        { status: 200 },
      ),
    );
    render(<AnalyticsPanel />);
    await waitFor(() => {
      expect(screen.getByText(/dp\.ε rem/i)).toBeInTheDocument();
    });
    expect(screen.getByText("4.00")).toBeInTheDocument();
    expect(screen.getByText(/sigs\.ok/i)).toBeInTheDocument();
    expect(screen.getByText("123")).toBeInTheDocument();
    expect(screen.getByText(/topics/i)).toBeInTheDocument();
    expect(screen.getByText(/explore·node·topology/)).toBeInTheDocument();
  });
});
