import { create } from "zustand";
import type { TickFrame } from "./frames";

/**
 * Concept taught: zustand keeps a single mutable store outside of React's
 * render cycle. Components subscribe to the slices they care about and
 * re-render only on those changes — which matters when we get 10 frames
 * per second.
 */

interface PenumbraState {
  connected: boolean;
  lastFrame: TickFrame | null;
  tickHistory: number[];
  setConnected: (connected: boolean) => void;
  ingestFrame: (frame: TickFrame) => void;
}

const HISTORY_DEPTH = 64;

export const usePenumbraStore = create<PenumbraState>((set) => ({
  connected: false,
  lastFrame: null,
  tickHistory: [],
  setConnected: (connected) => set({ connected }),
  ingestFrame: (frame) =>
    set((state) => ({
      lastFrame: frame,
      tickHistory:
        state.tickHistory.length >= HISTORY_DEPTH
          ? [...state.tickHistory.slice(1), frame.tick]
          : [...state.tickHistory, frame.tick],
    })),
}));
