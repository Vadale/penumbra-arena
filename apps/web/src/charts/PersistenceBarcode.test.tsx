import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PersistenceBarcode } from "./PersistenceBarcode";

describe("PersistenceBarcode", () => {
  it("renders a placeholder when both diagrams are empty", () => {
    render(<PersistenceBarcode h0Bars={[]} h1Bars={[]} />);
    expect(screen.getByText(/persistence diagram empty/i)).toBeInTheDocument();
  });

  it("renders H0 and H1 row labels when bars exist", () => {
    render(
      <PersistenceBarcode
        h0Bars={[
          [0, 1.0],
          [0, 0.5],
        ]}
        h1Bars={[[0.2, 0.8]]}
      />,
    );
    expect(screen.getByText("H₀")).toBeInTheDocument();
    expect(screen.getByText("H₁")).toBeInTheDocument();
  });

  it("renders an x-axis with the max death value as the right tick", () => {
    // Use a death value > 1 so the floor at 1 doesn't dominate.
    render(<PersistenceBarcode h0Bars={[[0, 2.5]]} h1Bars={[]} />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("2.50")).toBeInTheDocument();
  });
});
