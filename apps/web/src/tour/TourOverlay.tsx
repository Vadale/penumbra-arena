/**
 * First-run tour overlay.
 *
 * Walks the user through the four panels of the dashboard once. The
 * "seen" flag is persisted in localStorage so subsequent visits skip
 * it. Pressing Esc or clicking the backdrop also dismisses.
 */

import { useEffect, useState } from "react";

const STORAGE_KEY = "penumbra.tour.seen";

interface Step {
  title: string;
  body: string;
  emphasis: "left" | "bottom" | "middle" | "right";
}

const STEPS: Step[] = [
  {
    title: "1 / 4 · Arena",
    body: "The 3D view shows N=50 agents as fuzzy halos — radius and alpha encode recent position variance. The agents act under the MAPPO policy you trained earlier (random-walk if no checkpoint).",
    emphasis: "left",
  },
  {
    title: "2 / 4 · Coach",
    body: "Below the arena is the Coach panel. It runs `pna` (attacker CLI) and `psh` (shell tutor) inside the dashboard. Try `pna replay-cmd` or `psh lessons` for one-click learning.",
    emphasis: "bottom",
  },
  {
    title: "3 / 4 · Analytics",
    body: "12 streaming consumers — descriptive stats, ARIMA, HDBSCAN, persistent homology, Sinkhorn, Bayesian θ, DP budget, Dilithium sigs. All updated every second from the live tick stream.",
    emphasis: "middle",
  },
  {
    title: "4 / 4 · Chain",
    body: "The local PoS-VRF blockchain anchors match outcomes. Each block carries match results + any slashings + a BLS-aggregate finality bundle. `pna world save <name>` snapshots the whole thing.",
    emphasis: "right",
  },
];

export function TourOverlay() {
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const seen = window.localStorage.getItem(STORAGE_KEY) === "true";
    if (!seen) setVisible(true);
  }, []);

  useEffect(() => {
    if (!visible) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  });

  const dismiss = () => {
    setVisible(false);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, "true");
    }
  };

  const next = () => {
    if (step >= STEPS.length - 1) {
      dismiss();
      return;
    }
    setStep((s) => s + 1);
  };

  if (!visible) return null;

  const current = STEPS[step] ?? STEPS[0];
  if (!current) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-6">
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: backdrop dismissal is purely
          additive — primary controls (next/skip/done) are buttons */}
      <button
        type="button"
        aria-label="dismiss tour"
        onClick={dismiss}
        className="absolute inset-0 cursor-default bg-transparent"
      />
      <div
        className="relative w-full max-w-xl rounded-lg border border-slate-700 bg-slate-900 p-5 shadow-2xl"
        role="dialog"
        aria-modal="true"
      >
        <div className="mb-1 text-xs uppercase tracking-wider text-slate-500">{current.title}</div>
        <p className="mb-4 text-sm leading-relaxed text-slate-200">{current.body}</p>
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={dismiss}
            className="text-xs text-slate-500 hover:text-slate-300"
          >
            skip
          </button>
          <div className="flex items-center gap-2">
            {STEPS.map((s, i) => (
              <span
                key={s.emphasis}
                className={
                  i === step
                    ? "h-1.5 w-6 rounded bg-slate-200"
                    : "h-1.5 w-1.5 rounded-full bg-slate-700"
                }
              />
            ))}
            <button
              type="button"
              onClick={next}
              className="rounded bg-slate-200 px-3 py-1 text-xs font-medium text-slate-900 hover:bg-white"
            >
              {step >= STEPS.length - 1 ? "done" : "next"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
