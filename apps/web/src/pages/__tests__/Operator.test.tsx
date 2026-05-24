import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Operator } from "../Operator";

interface MockResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
  text: () => Promise<string>;
}

function jsonResponse(body: unknown, status = 200): MockResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

const ENABLED_STATUS = {
  enabled: true,
  operator_id: 50,
  position: 12,
  coins: 245.5,
  inventory: { bread: 3 },
  epsilon_total: 5.0,
  epsilon_spent: 0.1,
  epsilon_remaining: 4.9,
  queue: { pending: 0, submitted: 7, popped: 7 },
  recent_results: [],
  scorecard: {
    profit: 45.5,
    privacy_preserved: 0.98,
    attacks_survived: 0,
    chain_contribution: 2,
    composite: 0.61,
  },
};

describe("Operator console", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the four main panels when the operator is enabled", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((async () =>
      jsonResponse(ENABLED_STATUS)) as unknown as typeof fetch);

    render(<Operator />);

    expect(screen.getByRole("region", { name: /operator status/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /action builder/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /action log/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /score card/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("245.50")).toBeInTheDocument();
    });
    expect(screen.getByText(/bread:3/)).toBeInTheDocument();
    expect(screen.getByText(/0\.610/)).toBeInTheDocument();
  });

  it("shows the disabled hint when the operator slot is off", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((async () =>
      jsonResponse({
        enabled: false,
        hint: "POST /operator/enable first",
      })) as unknown as typeof fetch);

    render(<Operator />);

    await waitFor(() => {
      expect(screen.getByText(/operator is OFF/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /enable operator/i })).toBeInTheDocument();
  });

  it("submits the form against the matching /operator/<kind> endpoint", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(((
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url === "/operator/status") return Promise.resolve(jsonResponse(ENABLED_STATUS));
      if (url === "/operator/move" && init?.method === "POST") {
        return Promise.resolve(
          jsonResponse({
            kind: "move",
            success: true,
            data: { position: 14 },
            error: null,
            skipped: false,
            elapsed_ms: 1.2,
            applied_tick: 999,
          }),
        );
      }
      return Promise.resolve(jsonResponse({ enabled: true }));
    }) as unknown as typeof fetch);

    render(<Operator />);

    const targetInput = await screen.findByLabelText("target_node");
    fireEvent.change(targetInput, { target: { value: "14" } });
    fireEvent.click(screen.getByRole("button", { name: /^submit$/i }));

    await waitFor(() => {
      const moveCall = fetchSpy.mock.calls.find(
        ([url, init]) =>
          url === "/operator/move" &&
          typeof init === "object" &&
          init !== null &&
          (init as RequestInit).method === "POST",
      );
      expect(moveCall).toBeDefined();
      const body = JSON.parse((moveCall?.[1] as RequestInit).body as string);
      expect(body).toEqual({ target_node: 14 });
    });

    await waitFor(() => {
      expect(screen.getByText(/position=14/)).toBeInTheDocument();
    });
  });

  it("renders the resume banner when /operator/sessions/resumable says available", async () => {
    const resumablePayload = {
      available: true,
      session_id: "1779608000-abc",
      scenario_id: "scn-009-trade-bot-market-maker",
      scenario_label: "Trade-bot market maker",
      saved_at_tick: 1234,
      saved_at_wall_iso: "2026-05-24T12:00:00Z",
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(((
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url === "/operator/sessions/resumable")
        return Promise.resolve(jsonResponse(resumablePayload));
      if (url === "/operator/sessions/resume" && init?.method === "POST") {
        return Promise.resolve(jsonResponse({ resumed: true }));
      }
      if (url === "/operator/status") return Promise.resolve(jsonResponse(ENABLED_STATUS));
      return Promise.resolve(jsonResponse({ enabled: true }));
    }) as unknown as typeof fetch);

    render(<Operator />);

    const banner = await screen.findByRole("alert", { name: /resume your last session/i });
    expect(banner).toBeInTheDocument();
    expect(screen.getByText(/Trade-bot market maker/)).toBeInTheDocument();
    expect(screen.getByText(/tick 1234/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^resume$/i }));
    await waitFor(() => {
      const resumeCall = fetchSpy.mock.calls.find(
        ([url, init]) =>
          url === "/operator/sessions/resume" &&
          typeof init === "object" &&
          init !== null &&
          (init as RequestInit).method === "POST",
      );
      expect(resumeCall).toBeDefined();
    });
  });

  it("hides the banner when /operator/sessions/resumable says unavailable", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url === "/operator/sessions/resumable")
        return Promise.resolve(jsonResponse({ available: false }));
      if (url === "/operator/status") return Promise.resolve(jsonResponse(ENABLED_STATUS));
      return Promise.resolve(jsonResponse({}));
    }) as unknown as typeof fetch);

    render(<Operator />);

    // Wait a tick so the banner probe resolves and any banner would have
    // rendered already.
    await waitFor(() => {
      expect(screen.getByRole("region", { name: /operator status/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole("alert", { name: /resume your last session/i })).toBeNull();
  });

  it("re-polls /operator/status on the 1 s interval", async () => {
    vi.useFakeTimers();
    try {
      const fetchSpy = vi
        .spyOn(globalThis, "fetch")
        .mockImplementation((async () => jsonResponse(ENABLED_STATUS)) as unknown as typeof fetch);

      render(<Operator />);
      await vi.runOnlyPendingTimersAsync();
      const initial = fetchSpy.mock.calls.length;

      await vi.advanceTimersByTimeAsync(2500);
      expect(fetchSpy.mock.calls.length).toBeGreaterThan(initial);
    } finally {
      vi.useRealTimers();
    }
  });
});
