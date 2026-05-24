/**
 * Time-scrubber — rewind the arena view through the last N ticks.
 *
 * Concept taught: a strictly client-side replay UI. The websocket
 * keeps streaming live frames into a separate ring buffer
 * (frameHistory). This widget exposes a slider whose value is the
 * index into that buffer; flipping the cursor away from "live" tells
 * the arena views to read from history instead of the live frame.
 *
 * Visual:
 * - Wide horizontal slider (track + thumb).
 * - Major tick marks every 50 frames.
 * - A live-tick marker pinned at the rightmost position.
 * - Hover over the track shows the tick number under the cursor.
 * - "Live" snaps back; "Play" auto-advances the cursor at 1 Hz.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useReplayCursorStore } from "../stores/replayCursor";
import { useFrameHistoryStore } from "../streams/frameHistory";

const TICK_MAJOR_STEP = 50;
const PLAYBACK_MS = 1000;

export function TimeScrubber() {
  const frames = useFrameHistoryStore((s) => s.frames);
  const cursor = useReplayCursorStore((s) => s.cursor);
  const playing = useReplayCursorStore((s) => s.playing);
  const setCursor = useReplayCursorStore((s) => s.setCursor);
  const resumeLive = useReplayCursorStore((s) => s.resumeLive);
  const togglePlay = useReplayCursorStore((s) => s.togglePlay);
  const setPlaying = useReplayCursorStore((s) => s.setPlaying);

  const trackRef = useRef<HTMLDivElement | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const lastIndex = Math.max(0, frames.length - 1);
  const effectiveIndex = cursor === null ? lastIndex : Math.max(0, Math.min(lastIndex, cursor));
  const liveTick = frames[lastIndex]?.tick ?? null;
  const viewingTick = frames[effectiveIndex]?.tick ?? liveTick;

  // Playback: advance the cursor every PLAYBACK_MS ms; stop on reaching the end.
  useEffect(() => {
    if (!playing) return;
    if (cursor === null) {
      setPlaying(false);
      return;
    }
    const timer = window.setInterval(() => {
      const state = useReplayCursorStore.getState();
      const cur = state.cursor;
      const total = useFrameHistoryStore.getState().frames.length;
      if (cur === null) {
        state.setPlaying(false);
        return;
      }
      const next = cur + 1;
      if (next >= total - 1) {
        state.resumeLive();
        return;
      }
      state.setCursor(next);
      state.setPlaying(true);
    }, PLAYBACK_MS);
    return () => window.clearInterval(timer);
  }, [playing, cursor, setPlaying]);

  const onSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const idx = Number(e.target.value);
    if (idx >= lastIndex) {
      resumeLive();
    } else {
      setCursor(idx);
    }
  };

  const onMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const el = trackRef.current;
      if (el === null || lastIndex === 0) return;
      const rect = el.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      setHoverIndex(Math.round(ratio * lastIndex));
    },
    [lastIndex],
  );

  const hoverTick = hoverIndex !== null ? (frames[hoverIndex]?.tick ?? null) : null;

  const majorTicks = useMemo(() => {
    if (lastIndex <= 0) return [] as number[];
    const out: number[] = [];
    for (let i = 0; i <= lastIndex; i += TICK_MAJOR_STEP) out.push(i);
    if (out[out.length - 1] !== lastIndex) out.push(lastIndex);
    return out;
  }, [lastIndex]);

  const replaying = cursor !== null;

  if (frames.length === 0) {
    return (
      <div className="border-t border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] px-4 py-1.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        scrubber — waiting for frames…
      </div>
    );
  }

  return (
    <div
      className={
        replaying
          ? "border-t border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-4 py-1.5"
          : "border-t border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] px-4 py-1.5"
      }
    >
      <div className="flex items-center gap-3 text-[10px] uppercase tracking-wider">
        <span
          className={
            replaying
              ? "text-[color:var(--color-penumbra-ember)]"
              : "text-[color:var(--color-penumbra-cyan)]"
          }
        >
          {replaying ? "replay" : "live"}
        </span>
        <span className="tabular-nums text-[color:var(--color-penumbra-text)]">
          tick {viewingTick ?? "—"}
        </span>
        <span className="text-[color:var(--color-penumbra-dim)]">
          live: {liveTick ?? "—"} · buffer {frames.length}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={() => togglePlay()}
            disabled={!replaying}
            aria-label="Play back"
            className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-0.5 text-[9px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-40"
          >
            {playing ? "pause" : "play back"}
          </button>
          <button
            type="button"
            onClick={() => resumeLive()}
            aria-label="Resume Live"
            className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-0.5 text-[9px] uppercase text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            live
          </button>
        </div>
      </div>

      <div ref={trackRef} className="relative mt-1 h-6">
        <input
          type="range"
          min={0}
          max={lastIndex}
          step={1}
          value={effectiveIndex}
          onChange={onSliderChange}
          onMouseMove={onMove}
          onMouseLeave={() => setHoverIndex(null)}
          aria-label="Replay scrubber"
          className="absolute inset-x-0 top-2 h-2 w-full cursor-pointer appearance-none bg-[color:var(--color-penumbra-border)]"
        />
        {/* Major tick marks under the slider. */}
        <div className="pointer-events-none absolute inset-x-0 top-5 h-2">
          {majorTicks.map((idx) => {
            const ratio = lastIndex === 0 ? 0 : idx / lastIndex;
            return (
              <div
                key={`tick-${idx}`}
                className="absolute h-1 w-px bg-[color:var(--color-penumbra-muted)]"
                style={{ left: `${(ratio * 100).toFixed(2)}%` }}
              />
            );
          })}
        </div>
        {/* Live-tick star at the right edge. */}
        <div
          className="pointer-events-none absolute top-0 -translate-x-1/2 text-[10px] text-[color:var(--color-penumbra-cyan)]"
          style={{ left: "100%" }}
          aria-hidden
        >
          ★
        </div>
        {hoverTick !== null && (
          <div className="pointer-events-none absolute -top-3 left-2 text-[9px] tabular-nums text-[color:var(--color-penumbra-text)]">
            t={hoverTick}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Banner shown above the arena when the user is viewing a historical
 * frame. Lives alongside TimeScrubber and reads the same stores.
 */
export function ReplayBanner() {
  const cursor = useReplayCursorStore((s) => s.cursor);
  const resumeLive = useReplayCursorStore((s) => s.resumeLive);
  const frames = useFrameHistoryStore((s) => s.frames);

  if (cursor === null) return null;
  const lastIndex = Math.max(0, frames.length - 1);
  const viewingTick = frames[Math.max(0, Math.min(lastIndex, cursor))]?.tick ?? null;
  const liveTick = frames[lastIndex]?.tick ?? null;

  return (
    <div className="absolute left-1/2 top-3 z-20 flex -translate-x-1/2 items-center gap-2 border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-3 py-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)] shadow-lg">
      <span>replay mode</span>
      <span className="tabular-nums text-[color:var(--color-penumbra-text)]">
        viewing tick {viewingTick ?? "—"} · live {liveTick ?? "—"}
      </span>
      <button
        type="button"
        onClick={() => resumeLive()}
        className="border border-[color:var(--color-penumbra-ember)] px-1.5 py-0.5 text-[9px] uppercase text-[color:var(--color-penumbra-ember)] hover:text-[color:var(--color-penumbra-text)]"
      >
        resume live
      </button>
    </div>
  );
}
