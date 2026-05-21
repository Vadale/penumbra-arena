/**
 * `?` keyboard-shortcuts cheat-sheet overlay.
 *
 * Renders a centered modal that the user can dismiss with Escape,
 * backdrop click, or pressing `?` again. The shortcut list mirrors
 * what `useKeyboardShortcuts` actually wires up.
 */

import { useEffect } from "react";

interface Shortcut {
  keys: string;
  description: string;
}

const SHORTCUTS: Shortcut[] = [
  { keys: "1", description: "bottom panel → Coach (allow-listed pna/psh)" },
  { keys: "2", description: "bottom panel → Shell (real zsh via PTY)" },
  { keys: "3", description: "bottom panel → REPL (sandboxed Python)" },
  { keys: "g", description: "arena → toggle force-directed 2D ↔ 3D" },
  { keys: "p", description: "simulation → pause / resume" },
  { keys: "[", description: "time-warp ÷2 (slow down)" },
  { keys: "]", description: "time-warp ×2 (speed up)" },
  { keys: "?", description: "toggle this help overlay" },
  { keys: "Esc", description: "close any open overlay" },
];

export function HelpOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6">
      <button
        type="button"
        aria-label="dismiss help"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-transparent"
      />
      <div
        className="relative w-full max-w-md border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] p-5 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label="Penumbra keyboard shortcuts"
      >
        <div className="mb-3 flex items-baseline justify-between">
          <div className="text-xs uppercase tracking-[0.25em] text-[color:var(--color-penumbra-cyan)]">
            keyboard shortcuts
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-[11px] text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-text)]"
          >
            esc
          </button>
        </div>
        <table className="w-full font-mono text-[11px]">
          <tbody>
            {SHORTCUTS.map((s) => (
              <tr
                key={s.keys}
                className="border-b border-[color:var(--color-penumbra-border)] last:border-b-0"
              >
                <td className="w-12 py-1.5 text-[color:var(--color-penumbra-cyan)] tabular-nums">
                  {s.keys}
                </td>
                <td className="py-1.5 text-[color:var(--color-penumbra-text)]">{s.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-3 text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          shortcuts ignore typing inside text fields
        </div>
      </div>
    </div>
  );
}
