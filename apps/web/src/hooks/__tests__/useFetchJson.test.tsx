import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  type FetchState,
  type PollFetchState,
  useFetchJsonOnce,
  useFetchJsonPoll,
} from "../useFetchJson";

interface MockResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

function jsonResponse(body: unknown, status = 200): MockResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function brokenJsonResponse(status = 200): MockResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      throw new SyntaxError("Unexpected token");
    },
  };
}

interface Payload {
  hello: string;
}

function OnceProbe({ url }: { url: string }) {
  const state = useFetchJsonOnce<Payload>(url);
  return <div data-testid="probe">{describeOnce(state)}</div>;
}

function describeOnce<T>(state: FetchState<T>): string {
  if (state.kind === "data") return `data:${JSON.stringify(state.value)}`;
  if (state.kind === "error") return `error:${state.message}`;
  return state.kind;
}

function PollProbe({ url, intervalMs }: { url: string; intervalMs: number }) {
  const state = useFetchJsonPoll<Payload>(url, intervalMs);
  return <div data-testid="probe">{describePoll(state)}</div>;
}

function describePoll<T>(state: PollFetchState<T>): string {
  if (state.kind === "data") return `data:${JSON.stringify(state.value)}`;
  if (state.kind === "error") {
    if (state.lastValue !== undefined) {
      return `error+stale:${state.message}:${JSON.stringify(state.lastValue)}`;
    }
    return `error:${state.message}`;
  }
  return state.kind;
}

describe("useFetchJsonOnce", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("transitions loading -> data on a 200 OK", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((async () =>
      jsonResponse({ hello: "world" })) as unknown as typeof fetch);

    render(<OnceProbe url="/api/ok" />);

    await waitFor(() => {
      expect(screen.getByTestId("probe").textContent).toBe('data:{"hello":"world"}');
    });
  });

  it("transitions loading -> error on HTTP non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((async () =>
      jsonResponse({ err: true }, 500)) as unknown as typeof fetch);

    render(<OnceProbe url="/api/boom" />);

    await waitFor(() => {
      expect(screen.getByTestId("probe").textContent).toBe("error:HTTP 500 on /api/boom");
    });
  });

  it("transitions loading -> error on network throw", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((async () => {
      throw new Error("offline");
    }) as unknown as typeof fetch);

    render(<OnceProbe url="/api/down" />);

    await waitFor(() => {
      expect(screen.getByTestId("probe").textContent).toBe("error:network error: offline");
    });
  });

  it("transitions loading -> error on JSON parse failure", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((async () =>
      brokenJsonResponse()) as unknown as typeof fetch);

    render(<OnceProbe url="/api/garbage" />);

    await waitFor(() => {
      expect(screen.getByTestId("probe").textContent).toBe("error:invalid JSON from /api/garbage");
    });
  });

  it("aborts the in-flight request on unmount", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(((
      _url: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          const err = new DOMException("aborted", "AbortError");
          reject(err);
        });
      });
    }) as unknown as typeof fetch);

    const { unmount } = render(<OnceProbe url="/api/slow" />);
    expect(screen.getByTestId("probe").textContent).toBe("loading");
    unmount();
    const call = fetchSpy.mock.calls[0];
    expect(call).toBeDefined();
    const signal = (call?.[1] as RequestInit | undefined)?.signal;
    expect(signal?.aborted).toBe(true);
  });
});

describe("useFetchJsonPoll", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("retains last successful value on subsequent error and surfaces both", async () => {
    let call = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation((async () => {
      call += 1;
      if (call === 1) return jsonResponse({ hello: "first" });
      return jsonResponse({ err: true }, 503);
    }) as unknown as typeof fetch);

    render(<PollProbe url="/api/flaky" intervalMs={30} />);

    await waitFor(() => {
      expect(screen.getByTestId("probe").textContent).toBe('data:{"hello":"first"}');
    });

    await waitFor(
      () => {
        expect(screen.getByTestId("probe").textContent).toBe(
          'error+stale:HTTP 503 on /api/flaky:{"hello":"first"}',
        );
      },
      { timeout: 2000 },
    );
  });
});
