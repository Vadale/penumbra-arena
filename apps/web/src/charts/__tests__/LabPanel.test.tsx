// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useLabHistoryStore } from "../../stores/labHistory";
import { LabPanel } from "../LabPanel";

interface InjectBody {
  kind: string;
  payload: Record<string, unknown>;
}

function mockInjectOk(tick: number) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/control/inject")) {
      const body = JSON.parse(String(init?.body ?? "{}")) as InjectBody;
      return Promise.resolve(
        new Response(JSON.stringify({ ok: true, kind: body.kind, tick, payload: body.payload }), {
          status: 200,
        }),
      );
    }
    if (url.includes("/control/step")) {
      return Promise.resolve(
        new Response(JSON.stringify({ previous_tick: 100, new_tick: 101, tick: 101 }), {
          status: 200,
        }),
      );
    }
    return Promise.resolve(new Response("not found", { status: 404 }));
  });
}

function mockInjectError() {
  return vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response("server boom", { status: 500 }));
}

describe("LabPanel", () => {
  beforeEach(() => {
    useLabHistoryStore.setState({ history: [] });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    useLabHistoryStore.setState({ history: [] });
  });

  it("renders 4 inject buttons + 3 step buttons", () => {
    render(<LabPanel />);
    expect(screen.getByRole("button", { name: /trigger cpi shock/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /force garch spike/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /block agent #/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /slash validator #/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^step 1$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^step 10$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^step 100$/i })).toBeInTheDocument();
  });

  it("Trigger CPI shock POSTs to /control/inject with right payload", async () => {
    const spy = mockInjectOk(142);
    render(<LabPanel />);
    fireEvent.click(screen.getByRole("button", { name: /trigger cpi shock/i }));
    await waitFor(() => {
      expect(spy).toHaveBeenCalled();
    });
    const call = spy.mock.calls.find((c) => String(c[0]).includes("/control/inject"));
    expect(call).toBeDefined();
    if (!call) return;
    const init = call[1] as RequestInit | undefined;
    expect(init?.method).toBe("POST");
    const body = JSON.parse(String(init?.body ?? "{}")) as InjectBody;
    expect(body.kind).toBe("cpi.shock");
    expect(body.payload).toEqual({ ratio: 1.5 });
  });

  it("recent injections list updates after a successful POST", async () => {
    mockInjectOk(142);
    render(<LabPanel />);
    expect(screen.getByText(/no injections fired yet/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /trigger cpi shock/i }));
    await waitFor(() => {
      expect(screen.getByText(/✓ cpi\.shock fired at tick 142/)).toBeInTheDocument();
    });
    // History list also lands an entry (kind label + payload).
    expect(screen.getByText("cpi.shock")).toBeInTheDocument();
    expect(screen.getByText(/\{"ratio":1\.5\}/)).toBeInTheDocument();
  });

  it("error path surfaces the message", async () => {
    mockInjectError();
    render(<LabPanel />);
    fireEvent.click(screen.getByRole("button", { name: /trigger cpi shock/i }));
    await waitFor(() => {
      expect(screen.getByText(/HTTP 500 on \/control\/inject/i)).toBeInTheDocument();
    });
  });
});
