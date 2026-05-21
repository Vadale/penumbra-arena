import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReplConsole } from "./ReplConsole";

describe("ReplConsole", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the checking placeholder before /repl/status resolves", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise(() => {}) as never);
    render(<ReplConsole />);
    expect(screen.getByText(/checking REPL availability/i)).toBeInTheDocument();
  });

  it("renders the disabled message when REPL is off", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ enabled: false }), { status: 200 }),
    );
    render(<ReplConsole />);
    await waitFor(() => {
      expect(screen.getByText(/Python REPL disabled/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/PENUMBRA_ENABLE_REPL=1/)).toBeInTheDocument();
  });
});
