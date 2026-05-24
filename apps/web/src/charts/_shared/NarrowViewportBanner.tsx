/**
 * Narrow-viewport advisory banner.
 *
 * Penumbra targets desktop researchers (≥ 1100 px) and the layout in
 * `index.css` enforces a `min-width: 1100px; overflow-x: auto` body
 * guard so it scrolls horizontally below that. This banner makes the
 * trade-off visible instead of letting the user wonder why the chain
 * panel is off-screen.
 *
 * Dismissible — once dismissed, the choice is remembered in
 * localStorage (`penumbra.narrow.dismissed`) and the banner does not
 * re-show on subsequent narrow resizes in the same browser profile.
 */

import { useEffect, useState } from "react";

const STORAGE_KEY = "penumbra.narrow.dismissed";
const BREAKPOINT = 1100;

function readDismissed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeDismissed(): void {
  try {
    localStorage.setItem(STORAGE_KEY, "1");
  } catch {
    // ignore — private mode / quota
  }
}

export function NarrowViewportBanner() {
  const [hidden, setHidden] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    return readDismissed() || window.innerWidth >= BREAKPOINT;
  });

  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth >= BREAKPOINT) {
        setHidden(true);
      } else if (!readDismissed()) {
        setHidden(false);
      }
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
    };
  }, []);

  if (hidden) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="sticky top-0 z-40 flex items-center justify-between gap-3 border-b border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-3 py-1 text-xs text-[color:var(--color-penumbra-ember)]"
    >
      <span className="truncate">
        Penumbra dashboard targets desktop (≥ {BREAKPOINT} px). The view will scroll horizontally.
      </span>
      <button
        type="button"
        aria-label="Dismiss viewport warning"
        onClick={() => {
          writeDismissed();
          setHidden(true);
        }}
        className="shrink-0 rounded-sm border border-[color:var(--color-penumbra-ember)] px-2 py-0.5 text-xs uppercase tracking-wider hover:bg-[color:var(--color-penumbra-ember)] hover:text-[color:var(--color-penumbra-bg)]"
      >
        dismiss
      </button>
    </div>
  );
}
