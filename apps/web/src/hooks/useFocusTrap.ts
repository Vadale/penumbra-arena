/**
 * Focus-trap hook for dialogs / modals / overlays.
 *
 * Keeps Tab and Shift-Tab cycling inside `containerRef` while `active`
 * is true. Stores the element that had focus before activation and
 * restores it on deactivation. Also moves focus to the first focusable
 * descendant on activation so keyboard users land inside the dialog
 * instead of leaving focus on the trigger.
 */

import { type RefObject, useEffect } from "react";

const FOCUSABLE_SELECTOR =
  'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export function useFocusTrap(containerRef: RefObject<HTMLElement | null>, active: boolean): void {
  useEffect(() => {
    if (!active) return;
    const container = containerRef.current;
    if (!container) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;

    const focusables = (): HTMLElement[] =>
      Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
        (el) => !el.hasAttribute("disabled"),
      );

    const initial = focusables()[0];
    initial?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (!first || !last) return;
      const current = document.activeElement as HTMLElement | null;
      if (e.shiftKey && current === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && current === last) {
        e.preventDefault();
        first.focus();
      }
    };

    container.addEventListener("keydown", onKey);
    return () => {
      container.removeEventListener("keydown", onKey);
      previouslyFocused?.focus();
    };
  }, [containerRef, active]);
}
