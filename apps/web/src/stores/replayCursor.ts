/**
 * Replay-cursor store.
 *
 * Concept taught: a single source of truth for "which historical tick
 * is the arena currently displaying?". `cursor === null` means follow
 * the live tick (default). Any integer index in [0, frames.length-1]
 * pins the arena to that historical frame from the frameHistory ring.
 *
 * Playback (auto-advance) is also driven from here so the play button
 * and the arena views agree on a single piece of state.
 */

import { create } from "zustand";

interface ReplayCursorState {
  cursor: number | null;
  playing: boolean;
  setCursor: (cursor: number | null) => void;
  resumeLive: () => void;
  togglePlay: () => void;
  setPlaying: (playing: boolean) => void;
}

export const useReplayCursorStore = create<ReplayCursorState>((set) => ({
  cursor: null,
  playing: false,
  setCursor: (cursor) => set({ cursor, playing: false }),
  resumeLive: () => set({ cursor: null, playing: false }),
  togglePlay: () => set((s) => ({ playing: !s.playing })),
  setPlaying: (playing) => set({ playing }),
}));
