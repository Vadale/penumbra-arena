// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { TourOverlay } from "./TourOverlay";

describe("TourOverlay", () => {
  beforeEach(() => {
    globalThis.localStorage.clear();
  });

  it("renders the first step when no seen flag is set", () => {
    render(<TourOverlay />);
    expect(screen.getByText(/1 \/ 6 · Arena/i)).toBeInTheDocument();
  });

  it("does not render when the seen flag is set in localStorage", () => {
    globalThis.localStorage.setItem("penumbra.tour.seen", "true");
    render(<TourOverlay />);
    expect(screen.queryByText(/Arena/i)).not.toBeInTheDocument();
  });

  it("advances through all 6 steps and dismisses at the end", () => {
    render(<TourOverlay />);
    expect(screen.getByText(/1 \/ 6 · Arena/)).toBeInTheDocument();
    // 5 next-clicks take us through steps 2..6; the 6th click is on
    // "done" and dismisses.
    for (let i = 0; i < 5; i += 1) {
      fireEvent.click(screen.getByText("next"));
    }
    expect(screen.getByText(/6 \/ 6/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("done"));
    expect(screen.queryByText(/Arena/i)).not.toBeInTheDocument();
    expect(globalThis.localStorage.getItem("penumbra.tour.seen")).toBe("true");
  });

  it("skip persists the seen flag without finishing", () => {
    render(<TourOverlay />);
    fireEvent.click(screen.getByText("skip"));
    expect(globalThis.localStorage.getItem("penumbra.tour.seen")).toBe("true");
  });
});
