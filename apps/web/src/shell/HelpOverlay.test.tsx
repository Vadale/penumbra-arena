import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HelpOverlay } from "./HelpOverlay";

describe("HelpOverlay", () => {
  it("renders nothing when open=false", () => {
    const { container } = render(<HelpOverlay open={false} onClose={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the shortcut list when open", () => {
    render(<HelpOverlay open onClose={() => {}} />);
    expect(screen.getByText(/keyboard shortcuts/i)).toBeInTheDocument();
    // Should list every key from SHORTCUTS:
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("?")).toBeInTheDocument();
    expect(screen.getByText("Esc")).toBeInTheDocument();
  });

  it("calls onClose when the visible Close button is clicked", () => {
    const onClose = vi.fn();
    render(<HelpOverlay open onClose={onClose} />);
    fireEvent.click(screen.getByLabelText("Close"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when the aria-hidden backdrop is clicked", () => {
    const onClose = vi.fn();
    render(<HelpOverlay open onClose={onClose} />);
    const backdrops = document.querySelectorAll<HTMLElement>(
      'div[aria-hidden="true"].absolute.inset-0',
    );
    expect(backdrops).toHaveLength(1);
    const backdrop = backdrops[0];
    if (!backdrop) return;
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("does NOT call onClose when a click happens inside the dialog content", () => {
    const onClose = vi.fn();
    render(<HelpOverlay open onClose={onClose} />);
    // Click on the heading text, which is inside the dialog, not the backdrop.
    fireEvent.click(screen.getByText(/keyboard shortcuts/i));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("calls onClose on Escape keydown", () => {
    const onClose = vi.fn();
    render(<HelpOverlay open onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });
});
