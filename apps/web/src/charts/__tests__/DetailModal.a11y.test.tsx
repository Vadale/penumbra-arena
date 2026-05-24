// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DetailModal } from "../DetailModal";

const safeValues = [1, 2, 3, 4, 5];

function getBackdrop(): HTMLElement {
  // The backdrop is the sibling div with aria-hidden="true" inside the modal
  // overlay. There is only one in the rendered tree.
  const backdrops = document.querySelectorAll<HTMLElement>(
    'div[aria-hidden="true"].absolute.inset-0',
  );
  if (backdrops.length !== 1 || !backdrops[0]) {
    throw new Error(`expected exactly one backdrop, got ${backdrops.length}`);
  }
  return backdrops[0];
}

describe("DetailModal accessibility — focus trap + backdrop dismiss", () => {
  it("focuses the first focusable element inside the dialog on open", () => {
    render(<DetailModal open onClose={() => {}} metric="dp_epsilon_spent" values={safeValues} />);
    const closeButton = screen.getByLabelText("Close");
    // useFocusTrap moves focus to the first focusable (the Close button).
    expect(document.activeElement).toBe(closeButton);
  });

  it("traps Tab focus inside the dialog (does not escape to document.body)", () => {
    render(
      <>
        <button type="button" data-testid="outside">
          outside
        </button>
        <DetailModal open onClose={() => {}} metric="dp_epsilon_spent" values={safeValues} />
      </>,
    );

    const dialog = screen.getByRole("dialog");
    const focusables = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      ),
    );
    expect(focusables.length).toBeGreaterThan(0);

    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    expect(first).toBeDefined();
    expect(last).toBeDefined();
    if (!first || !last) return;

    // Focus the last item and press Tab — should wrap to first.
    last.focus();
    expect(document.activeElement).toBe(last);
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(document.activeElement).toBe(first);
    expect(document.activeElement).not.toBe(screen.getByTestId("outside"));

    // Shift+Tab on first wraps to last.
    first.focus();
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it("calls onClose on Escape", () => {
    const onClose = vi.fn();
    render(<DetailModal open onClose={onClose} metric="dp_epsilon_spent" values={safeValues} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when the aria-hidden backdrop is clicked", () => {
    const onClose = vi.fn();
    render(<DetailModal open onClose={onClose} metric="dp_epsilon_spent" values={safeValues} />);
    fireEvent.click(getBackdrop());
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("does NOT call onClose when a click happens inside the dialog content", () => {
    const onClose = vi.fn();
    render(<DetailModal open onClose={onClose} metric="dp_epsilon_spent" values={safeValues} />);
    // Click the description text inside the dialog — should not dismiss.
    fireEvent.click(screen.getByText(/Differential-privacy/i));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("calls onClose when the visible Close button is clicked", () => {
    const onClose = vi.fn();
    render(<DetailModal open onClose={onClose} metric="dp_epsilon_spent" values={safeValues} />);
    fireEvent.click(screen.getByLabelText("Close"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("renders nothing when open=false", () => {
    const { container } = render(
      <DetailModal open={false} onClose={() => {}} metric="dp_epsilon_spent" values={safeValues} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
