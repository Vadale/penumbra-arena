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
    expect(screen.getByText(/1 \/ 4 · Arena/i)).toBeInTheDocument();
  });

  it("does not render when the seen flag is set in localStorage", () => {
    globalThis.localStorage.setItem("penumbra.tour.seen", "true");
    render(<TourOverlay />);
    expect(screen.queryByText(/Arena/i)).not.toBeInTheDocument();
  });

  it("advances through steps on next click and dismisses at the end", () => {
    render(<TourOverlay />);
    expect(screen.getByText(/1 \/ 4 · Arena/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("next"));
    expect(screen.getByText(/2 \/ 4 · Coach/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("next"));
    expect(screen.getByText(/3 \/ 4 · Analytics/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("next"));
    expect(screen.getByText(/4 \/ 4 · Chain/)).toBeInTheDocument();
    expect(screen.getByText("done")).toBeInTheDocument();
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
