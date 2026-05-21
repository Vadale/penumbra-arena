/**
 * Wires global keyboard shortcuts for the dashboard.
 *
 * Skips events whose target is a text input or contenteditable
 * element — typing into Coach/REPL/Terminal shouldn't trigger
 * panel switches.
 */

import { useEffect } from "react";

export interface ShortcutHandlers {
  onBottomTab: (tab: "coach" | "terminal" | "repl") => void;
  onArenaToggle: () => void;
  onPauseToggle: () => void;
  onTimeWarpDelta: (factor: number) => void;
  onHelpToggle: () => void;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  if (target.isContentEditable) return true;
  // xterm.js renders a hidden textarea inside `.xterm-helper-textarea`;
  // when the user focuses the terminal, that textarea has focus and
  // typing should NOT trigger shortcuts.
  if (target.closest(".xterm") !== null) return true;
  return false;
}

export function useKeyboardShortcuts(handlers: ShortcutHandlers): void {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTypingTarget(e.target)) return;

      switch (e.key) {
        case "1":
          handlers.onBottomTab("coach");
          break;
        case "2":
          handlers.onBottomTab("terminal");
          break;
        case "3":
          handlers.onBottomTab("repl");
          break;
        case "g":
        case "G":
          handlers.onArenaToggle();
          break;
        case "p":
        case "P":
          handlers.onPauseToggle();
          break;
        case "[":
          handlers.onTimeWarpDelta(0.5);
          break;
        case "]":
          handlers.onTimeWarpDelta(2.0);
          break;
        case "?":
          handlers.onHelpToggle();
          e.preventDefault();
          break;
        default:
          return;
      }
    };
    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
    };
  }, [handlers]);
}
