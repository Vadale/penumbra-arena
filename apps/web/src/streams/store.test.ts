import { beforeEach, describe, expect, it } from "vitest";
import { usePenumbraStore } from "./store";

describe("usePenumbraStore", () => {
  beforeEach(() => {
    // Reset to initial state between tests.
    usePenumbraStore.setState({
      connected: false,
      lastFrame: null,
      tickHistory: [],
      agentPositionHistory: {},
    });
  });

  it("ingests a frame and updates lastFrame + history", () => {
    usePenumbraStore.getState().ingestFrame({
      tick: 1,
      match_id: 0,
      match_status: "running",
      agent_positions: { 0: 5, 1: 7 },
      arena_edge_count: 12,
      arena_goals: [3],
    });
    const state = usePenumbraStore.getState();
    expect(state.lastFrame?.tick).toBe(1);
    expect(state.tickHistory).toEqual([1]);
    expect(state.agentPositionHistory[0]).toEqual([5]);
    expect(state.agentPositionHistory[1]).toEqual([7]);
  });

  it("accumulates per-agent position history across frames", () => {
    const store = usePenumbraStore.getState();
    for (let t = 1; t <= 3; t++) {
      store.ingestFrame({
        tick: t,
        match_id: 0,
        match_status: "running",
        agent_positions: { 0: t * 2 },
        arena_edge_count: 12,
        arena_goals: [],
      });
    }
    expect(usePenumbraStore.getState().agentPositionHistory[0]).toEqual([2, 4, 6]);
  });

  it("setConnected toggles the connection flag", () => {
    usePenumbraStore.getState().setConnected(true);
    expect(usePenumbraStore.getState().connected).toBe(true);
    usePenumbraStore.getState().setConnected(false);
    expect(usePenumbraStore.getState().connected).toBe(false);
  });
});
