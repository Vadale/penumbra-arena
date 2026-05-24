/**
 * One-shot welcome modal shown on a viewer's first visit to the
 * dashboard. Persists a `localStorage` flag so subsequent reloads
 * skip it immediately. Designed to fire BEFORE the longer
 * `TourOverlay` walks the user through individual panels.
 *
 * Lives alongside the analytics charts because it is itself a thin
 * UI surface — no domain logic, no fetches, no streams.
 */

import { useEffect, useState } from "react";

const STORAGE_KEY = "penumbra.welcome.seen";

export function WelcomeOverlay() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const seen = window.localStorage.getItem(STORAGE_KEY) === "1";
      if (!seen) setVisible(true);
    } catch {
      // localStorage can throw in private-browsing modes; default to showing.
      setVisible(true);
    }
  }, []);

  const dismiss = () => {
    setVisible(false);
    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(STORAGE_KEY, "1");
      } catch {
        // best-effort persistence; ignore quota errors
      }
    }
  };

  useEffect(() => {
    if (!visible) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [visible]);

  if (!visible) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="penumbra-welcome-title"
    >
      <button
        type="button"
        aria-label="Dismiss welcome"
        onClick={dismiss}
        className="absolute inset-0 cursor-default bg-transparent"
      />
      <div className="relative w-full max-w-lg rounded-lg border border-slate-700 bg-slate-900 p-6 shadow-2xl">
        <div className="mb-3 flex items-baseline justify-between">
          <h2
            id="penumbra-welcome-title"
            className="text-base font-semibold text-slate-100 tracking-tight"
          >
            Welcome to Penumbra
          </h2>
          <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500">v0.1</span>
        </div>
        <div className="space-y-3 text-sm leading-relaxed text-slate-300">
          <p>
            Penumbra is a privacy-preserving multi-agent arena. 50 agents trained with MAPPO compete
            on a procedurally-changing graph. You are watching them live.
          </p>
          <p>
            Their state is encrypted (CKKS). What you see is the ENCRYPTED view plus DP-noised
            aggregates &mdash; never the raw positions.
          </p>
          <p>
            Click any tile on the right to learn what is behind it. Click <strong>Operator</strong>{" "}
            in the top nav to play a cyber-range scenario yourself.
          </p>
          <p className="text-xs text-slate-400">
            Press <kbd className="rounded border border-slate-700 px-1">?</kbd> anytime for help.
            Default speed is 2 ticks per second &mdash; adjust with the speed widget at the top.
          </p>
        </div>
        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={dismiss}
            className="rounded bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            Get started
          </button>
        </div>
      </div>
    </div>
  );
}
