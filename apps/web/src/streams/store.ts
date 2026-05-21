import { create } from "zustand";
import type { TickFrame } from "./frames";

/**
 * Concept taught: zustand keeps a single mutable store outside of React's
 * render cycle. Components subscribe to the slices they care about and
 * re-render only on those changes — which matters when we get 10 frames
 * per second.
 *
 * In addition to the latest frame we keep a rolling per-agent position
 * history (last POSITIONS_DEPTH ticks). The Arena renders each agent's
 * uncertainty as a halo whose alpha scales with the recent variance of
 * that agent's position — a poor man's bayesian posterior σ that lives
 * entirely on the client.
 */

interface PenumbraState {
  connected: boolean;
  lastFrame: TickFrame | null;
  tickHistory: number[];
  agentPositionHistory: Record<number, number[]>;
  setConnected: (connected: boolean) => void;
  ingestFrame: (frame: TickFrame) => void;
}

const TICK_HISTORY_DEPTH = 64;
const POSITIONS_DEPTH = 24;

function pushBounded(values: number[], next: number): number[] {
  if (values.length >= POSITIONS_DEPTH) {
    return [...values.slice(1), next];
  }
  return [...values, next];
}

export const usePenumbraStore = create<PenumbraState>((set) => ({
  connected: false,
  lastFrame: null,
  tickHistory: [],
  agentPositionHistory: {},
  setConnected: (connected) => set({ connected }),
  ingestFrame: (frame) =>
    set((state) => {
      const nextHistory =
        state.tickHistory.length >= TICK_HISTORY_DEPTH
          ? [...state.tickHistory.slice(1), frame.tick]
          : [...state.tickHistory, frame.tick];

      const nextPositions = { ...state.agentPositionHistory };
      for (const [idStr, pos] of Object.entries(frame.agent_positions)) {
        const id = Number(idStr);
        const prior = nextPositions[id] ?? [];
        nextPositions[id] = pushBounded(prior, pos);
      }

      return {
        lastFrame: frame,
        tickHistory: nextHistory,
        agentPositionHistory: nextPositions,
      };
    }),
}));
