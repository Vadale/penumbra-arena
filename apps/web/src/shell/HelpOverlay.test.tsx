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

  it("calls onClose on dismiss-backdrop click", () => {
    const onClose = vi.fn();
    render(<HelpOverlay open onClose={onClose} />);
    fireEvent.click(screen.getByLabelText("dismiss help"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose on Escape keydown", () => {
    const onClose = vi.fn();
    render(<HelpOverlay open onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });
});
