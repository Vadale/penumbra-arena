// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SpeedControl } from "./SpeedControl";

describe("SpeedControl", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("polls /control/tick_hz on mount and highlights the active speed", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ tick_hz: 2.0, allowed: [0.5, 1, 2, 5, 10] }), {
        status: 200,
      }),
    );
    render(<SpeedControl paused={false} onPauseToggle={() => {}} />);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/control/tick_hz");
    });
    // The 2x button should land in the active-styled state.
    const twoX = await screen.findByRole("button", { name: "2x" });
    await waitFor(() => {
      expect(twoX.getAttribute("aria-pressed")).toBe("true");
    });
  });

  it("posts the chosen tick rate when a speed button is clicked", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ tick_hz: 2.0, allowed: [0.5, 1, 2, 5, 10] }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ tick_hz: 5.0, allowed: [0.5, 1, 2, 5, 10] }), {
          status: 200,
        }),
      );
    render(<SpeedControl paused={false} onPauseToggle={() => {}} />);
    const fiveX = await screen.findByRole("button", { name: "5x" });
    fireEvent.click(fiveX);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/control/tick_hz",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ tick_hz: 5 }),
        }),
      );
    });
  });

  it("invokes onPauseToggle when the pause/play button is clicked", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ tick_hz: 2.0, allowed: [0.5, 1, 2, 5, 10] }), {
        status: 200,
      }),
    );
    const onPause = vi.fn();
    render(<SpeedControl paused={false} onPauseToggle={onPause} />);
    fireEvent.click(screen.getByRole("button", { name: "pause" }));
    expect(onPause).toHaveBeenCalledTimes(1);
  });
});
