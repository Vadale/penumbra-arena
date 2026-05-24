// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { WelcomeOverlay } from "./WelcomeOverlay";

describe("WelcomeOverlay", () => {
  beforeEach(() => {
    globalThis.localStorage.clear();
  });

  it("shows on first visit when no seen flag is set", () => {
    render(<WelcomeOverlay />);
    expect(screen.getByText(/Welcome to Penumbra/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /get started/i })).toBeInTheDocument();
  });

  it("does not show on second visit when seen flag is set", () => {
    globalThis.localStorage.setItem("penumbra.welcome.seen", "1");
    render(<WelcomeOverlay />);
    expect(screen.queryByText(/Welcome to Penumbra/i)).not.toBeInTheDocument();
  });

  it("dismiss + persists the seen flag", () => {
    render(<WelcomeOverlay />);
    fireEvent.click(screen.getByRole("button", { name: /get started/i }));
    expect(screen.queryByText(/Welcome to Penumbra/i)).not.toBeInTheDocument();
    expect(globalThis.localStorage.getItem("penumbra.welcome.seen")).toBe("1");
  });
});
