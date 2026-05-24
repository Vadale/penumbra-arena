/**
 * Effective-frame hook.
 *
 * Concept taught: the arena views shouldn't care whether they're
 * rendering the live tick or a replayed historical tick. This hook
 * encapsulates the decision: if the replay cursor is null, hand back
 * the live `lastFrame`; otherwise, hand back the frame at that index
 * in the recorded history (clamped to the buffer's bounds).
 *
 * The arena views call this instead of reading lastFrame directly —
 * a one-line swap keeps them oblivious to replay mode entirely.
 */

import { useReplayCursorStore } from "../stores/replayCursor";
import { useFrameHistoryStore } from "./frameHistory";
import type { TickFrame } from "./frames";
import { usePenumbraStore } from "./store";

export function useEffectiveFrame(): TickFrame | null {
  const live = usePenumbraStore((s) => s.lastFrame);
  const cursor = useReplayCursorStore((s) => s.cursor);
  const frames = useFrameHistoryStore((s) => s.frames);
  if (cursor === null) return live;
  if (frames.length === 0) return live;
  const clamped = Math.max(0, Math.min(frames.length - 1, cursor));
  return frames[clamped] ?? live;
}
