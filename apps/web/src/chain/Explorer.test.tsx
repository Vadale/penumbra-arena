import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChainExplorer } from "./Explorer";

describe("ChainExplorer", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the connecting placeholder before any poll succeeds", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise(() => {}) as never);
    render(<ChainExplorer />);
    expect(screen.getByText(/chain explorer connecting/i)).toBeInTheDocument();
  });

  it("renders the height-0 message when /chain/latest reports an empty chain", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ height: 0, blocks: [] }), { status: 200 }),
    );
    render(<ChainExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/chain height 0/i)).toBeInTheDocument();
    });
  });

  it("renders a block card including its slashings", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          height: 1,
          head_hash: "deadbeef",
          blocks: [
            {
              hash: "abc123def456fed789",
              height: 1,
              prev_hash: "0000",
              merkle_root: "1111",
              proposer_pubkey: "feedface",
              timestamp_ns: 1234567,
              outcomes: [{ match_id: 7, winner_agent_id: 3, end_tick: 42, end_reason: "won" }],
              slashings: [{ offender_pubkey: "deadbeef…", height_observed: 1 }],
              validator_count: 4,
            },
          ],
        }),
        { status: 200 },
      ),
    );
    render(<ChainExplorer />);
    await waitFor(() => {
      expect(screen.getByText(/block #1/)).toBeInTheDocument();
    });
    expect(screen.getByText(/match 7/)).toBeInTheDocument();
    expect(screen.getByText(/slashed/i)).toBeInTheDocument();
    expect(screen.getByText(/deadbeef…/)).toBeInTheDocument();
  });
});
