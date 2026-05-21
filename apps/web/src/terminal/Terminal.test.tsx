import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Terminal } from "./Terminal";

describe("Terminal", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the checking placeholder before /pty/status resolves", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise(() => {}) as never);
    render(<Terminal />);
    expect(screen.getByText(/checking PTY availability/i)).toBeInTheDocument();
  });

  it("renders the disabled message when PTY is off", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ enabled: false }), { status: 200 }),
    );
    render(<Terminal />);
    await waitFor(() => {
      expect(screen.getByText(/PTY shell disabled/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/PENUMBRA_ENABLE_PTY=1/)).toBeInTheDocument();
  });
});
