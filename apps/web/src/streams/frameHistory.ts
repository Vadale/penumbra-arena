/**
 * Rolling frame-history store.
 *
 * Concept taught: a ring buffer of the last N WebSocket TickFrames so
 * the time-scrubber can rewind the arena view without touching the
 * live websocket ingest path. The buffer is fed by a separate
 * subscriber hook (useFrameHistoryRecorder) that watches the main
 * penumbra store's lastFrame slice and appends a copy on each new
 * tick. This way the WS pipeline stays single-purpose and the replay
 * layer is purely additive.
 */

import { useEffect } from "react";
import { create } from "zustand";
import type { TickFrame } from "./frames";
import { usePenumbraStore } from "./store";

const HISTORY_CAPACITY = 500;

interface FrameHistoryState {
  frames: TickFrame[];
  append: (frame: TickFrame) => void;
  clear: () => void;
}

export const useFrameHistoryStore = create<FrameHistoryState>((set) => ({
  frames: [],
  append: (frame) =>
    set((state) => {
      const last = state.frames[state.frames.length - 1];
      if (last !== undefined && last.tick === frame.tick) return state;
      const next =
        state.frames.length >= HISTORY_CAPACITY
          ? [...state.frames.slice(1), frame]
          : [...state.frames, frame];
      return { frames: next };
    }),
  clear: () => set({ frames: [] }),
}));

/**
 * Mount once at the dashboard root. Subscribes to the live frame
 * slice and appends each unique tick into the history ring.
 */
export function useFrameHistoryRecorder(): void {
  const lastFrame = usePenumbraStore((s) => s.lastFrame);
  const append = useFrameHistoryStore((s) => s.append);
  useEffect(() => {
    if (lastFrame === null) return;
    append(lastFrame);
  }, [lastFrame, append]);
}

export const FRAME_HISTORY_CAPACITY = HISTORY_CAPACITY;
