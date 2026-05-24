/**
 * Inline speed widget for the dashboard header.
 *
 * Calls GET /control/tick_hz on mount to discover the live rate +
 * curated ladder, and POSTs to /control/tick_hz when the operator
 * picks a button. The pause button uses the existing /control/pause
 * and /control/resume endpoints so we don't duplicate state.
 *
 * Exposes the current tick rate to ancestors via the optional
 * `onRateChange` callback so the arena caption can show a live "speed:
 * 2 Hz" label without polling a second time.
 */

import { useEffect, useState } from "react";
import { useAchievementsStore } from "../stores/achievements";

interface TickHzPayload {
  tick_hz: number;
  allowed: number[];
}

const FALLBACK_ALLOWED = [0.5, 1, 2, 5, 10];

export function SpeedControl({
  paused,
  onPauseToggle,
  onRateChange,
}: {
  paused: boolean;
  onPauseToggle: () => void;
  onRateChange?: (hz: number) => void;
}) {
  const [tickHz, setTickHz] = useState<number | null>(null);
  const [allowed, setAllowed] = useState<number[]>(FALLBACK_ALLOWED);
  const [busy, setBusy] = useState(false);
  const markSpeedUsed = useAchievementsStore((s) => s.markSpeedUsed);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const r = await fetch("/control/tick_hz");
        if (!r.ok) return;
        const body = (await r.json()) as TickHzPayload;
        if (cancelled) return;
        setTickHz(body.tick_hz);
        if (Array.isArray(body.allowed) && body.allowed.length > 0) {
          setAllowed(body.allowed);
        }
        onRateChange?.(body.tick_hz);
      } catch {
        // ignore; controls still render with the fallback ladder
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [onRateChange]);

  const choose = async (hz: number) => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await fetch("/control/tick_hz", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tick_hz: hz }),
      });
      if (r.ok) {
        const body = (await r.json()) as TickHzPayload;
        setTickHz(body.tick_hz);
        onRateChange?.(body.tick_hz);
        markSpeedUsed(String(body.tick_hz));
      }
    } catch {
      // ignore; next click will retry
    } finally {
      setBusy(false);
    }
  };

  return (
    <fieldset
      aria-label="Simulation speed"
      className="flex items-center gap-1 rounded-sm border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1.5 py-0.5"
    >
      <span className="pr-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        speed
      </span>
      <button
        type="button"
        onClick={onPauseToggle}
        title={paused ? "resume" : "pause"}
        aria-pressed={paused}
        className={
          paused
            ? "border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)]"
            : "border border-[color:var(--color-penumbra-border)] px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-text)]"
        }
      >
        {paused ? "play" : "pause"}
      </button>
      {allowed.map((hz) => {
        const active = tickHz !== null && Math.abs(tickHz - hz) < 1e-6;
        return (
          <button
            key={hz}
            type="button"
            onClick={() => void choose(hz)}
            disabled={busy}
            aria-pressed={active}
            title={`${hz} ticks per second`}
            className={
              active
                ? "border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-1.5 py-0.5 text-[10px] tabular-nums uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]"
                : "border border-[color:var(--color-penumbra-border)] px-1.5 py-0.5 text-[10px] tabular-nums uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-text)] disabled:opacity-50"
            }
          >
            {formatHz(hz)}
          </button>
        );
      })}
    </fieldset>
  );
}

function formatHz(hz: number): string {
  if (hz >= 1) return `${hz}x`;
  // 0.5 -> ".5x" reads cleaner than "0.5x" at the small font size.
  return `${hz.toString().replace(/^0/, "")}x`;
}
