import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CoachConsole } from "./Console";

describe("CoachConsole", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders preset buttons once /coach/presets resolves", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          attacker: [
            { label: "replay attack", command: "pna replay-cmd" },
            { label: "byzantine equivocation", command: "pna byzantine-cmd" },
          ],
          shell: [{ label: "lessons", command: "psh lessons" }],
        }),
        { status: 200 },
      ),
    );
    render(<CoachConsole />);
    await waitFor(() => {
      expect(screen.getByText(/replay attack/)).toBeInTheDocument();
    });
    expect(screen.getByText(/byzantine equivocation/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^lessons$/ })).toBeInTheDocument();
  });
});
