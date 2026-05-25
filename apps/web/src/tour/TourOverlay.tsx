/**
 * First-run tour overlay.
 *
 * Walks the user through the four panels of the dashboard once. The
 * "seen" flag is persisted in localStorage so subsequent visits skip
 * it. Pressing Esc or clicking the backdrop also dismisses.
 *
 * Accessibility: focus is trapped inside the dialog while visible and
 * restored on close; the backdrop is `aria-hidden` so screen readers
 * announce the dialog content first.
 */

import { useEffect, useRef, useState } from "react";
import { useFocusTrap } from "../hooks/useFocusTrap";

const STORAGE_KEY = "penumbra.tour.seen";

interface Step {
  title: string;
  body: string;
  emphasis: "left" | "bottom" | "middle" | "right";
}

const STEPS: Step[] = [
  {
    title: "1 / 7 · Arena (left)",
    body: "N=50 agents on a procedurally dynamic graph. The DF-style tile map renders fuzzy halos sized by recent position variance. Agents act under the live MAPPO policy — toggle MAPPO/RANDOM in the status bar to switch on the fly.",
    emphasis: "left",
  },
  {
    title: "2 / 7 · Status bar (bottom)",
    body: "Live counters: tick, match, chain height, DP ε remaining, signing stats. The two interactive controls on the right are the MAPPO/RANDOM toggle and the temperature slider — they mutate the live inference policy without restart.",
    emphasis: "bottom",
  },
  {
    title: "3 / 7 · Coach console (bottom)",
    body: "In-dashboard runner for pna (attacker CLI) + psh (shell tutor) + pno (operator). 12 attack chips, 19 shell lessons, all reachable without leaving the browser. Switch to the 'shell' tab for a live macOS zsh PTY or 'repl' for a sandboxed Python REPL with pna.api pre-imported.",
    emphasis: "bottom",
  },
  {
    title: "4 / 7 · Three CLIs you can install",
    body: "If you prefer your own terminal: `uv tool install ./packages/{attacker,shell_coach,operator}` exposes `pna` (12 attacks), `psh` (19 lessons + explain/suggest/interpret), and `pno` (20 operator actions + 12 scenarios). All three honour PENUMBRA_API_URL so one export points them at the running stack.",
    emphasis: "bottom",
  },
  {
    title: "5 / 7 · Analytics tiles (right)",
    body: "99 clickable tiles in 12 sections — start with statistics + econometrics + economy (the 'essentials' band at the top); the rest (crypto, defenses, attacks, federated, logistics, interactive) is opt-in depth. Clicking any tile opens a detail modal with the educational description, the live chart, and a 'try it in your shell' CLI snippet.",
    emphasis: "right",
  },
  {
    title: "6 / 7 · ML interaction",
    body: "Click 'MAPPO π' for the policy inspector, 'training' for live PPO start/stop + curves, 'V(s)' for critic + per-node entropy, 'reward' for live reward shaping sliders, 'A/B π' to load a second checkpoint.",
    emphasis: "right",
  },
  {
    title: "7 / 7 · Crypto & chain",
    body: "Click 'ZK proof' for Groth16 verify ACCEPT vs REJECT, 'BLS agg' to inspect block signatures, 'Kyber'/'Dilithium' for PQ key sizes, 'VDF' for the compute/verify asymmetry, 'Shamir' for secret splitting, 'snapshots' to save/load the perpetual state.",
    emphasis: "right",
  },
];

export function TourOverlay() {
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  useFocusTrap(dialogRef, visible);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const seen = window.localStorage.getItem(STORAGE_KEY) === "true";
    if (!seen) setVisible(true);
  }, []);

  const dismiss = () => {
    setVisible(false);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, "true");
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
      {/* Backdrop: clickable to dismiss, hidden from screen readers so the */}
      {/* dialog content is announced first; the explicit "Close" button is */}
      {/* the SR-discoverable dismiss. Esc also dismisses via the effect above. */}
      <div
        aria-hidden="true"
        onClick={dismiss}
        className="absolute inset-0 cursor-default bg-transparent"
      />
      <div
        ref={dialogRef}
        className="relative w-full max-w-xl rounded-lg border border-slate-700 bg-slate-900 p-5 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label="Penumbra first-run tour"
      >
        <div className="mb-1 flex items-start justify-between">
          <div className="text-xs uppercase tracking-wider text-slate-500">{current.title}</div>
          <button
            type="button"
            aria-label="Close"
            onClick={dismiss}
            className="text-[14px] leading-none text-slate-500 hover:text-slate-200"
          >
            {"×"}
          </button>
        </div>
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
