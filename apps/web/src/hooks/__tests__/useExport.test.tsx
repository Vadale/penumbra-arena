// @vitest-environment jsdom
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { useExport } from "../useExport";

beforeAll(() => {
  // jsdom 25 does not implement blob URL helpers; provide stubs so the
  // download dance can be spied on without crashing in the hook.
  if (typeof URL.createObjectURL !== "function") {
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: () => "blob:stub",
    });
  }
  if (typeof URL.revokeObjectURL !== "function") {
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: () => {},
    });
  }
});

interface MockBlobResponse {
  ok: boolean;
  status: number;
  blob: () => Promise<Blob>;
}

function okBlob(body: string, type = "text/csv"): MockBlobResponse {
  return {
    ok: true,
    status: 200,
    blob: async () => new Blob([body], { type }),
  };
}

function failResponse(status: number): MockBlobResponse {
  return {
    ok: false,
    status,
    blob: async () => new Blob([]),
  };
}

interface ProbeApi {
  download: ReturnType<typeof useExport>["download"];
}

function Probe({ metric, expose }: { metric: string; expose: (api: ProbeApi) => void }) {
  const result = useExport(metric);
  expose({ download: result.download });
  return (
    <div>
      <div data-testid="state">
        {result.isExporting ? "exporting" : "idle"}
        {result.error ? `|error:${result.error}` : ""}
      </div>
    </div>
  );
}

describe("useExport", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("csv format fetches the right URL and triggers a blob download", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((async () => okBlob("a,b\n1,2\n")) as unknown as typeof fetch);
    const createUrlSpy = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fake-url-csv");
    const revokeUrlSpy = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    let api: ProbeApi | undefined;
    render(
      <Probe
        metric="inflation"
        expose={(a) => {
          api = a;
        }}
      />,
    );
    expect(api).toBeDefined();
    if (!api) return;

    await act(async () => {
      await api?.download("csv");
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const call = fetchSpy.mock.calls[0];
    expect(call).toBeDefined();
    expect(call?.[0]).toBe("/export/chart/inflation?format=csv");
    expect(createUrlSpy).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeUrlSpy).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("state").textContent).toBe("idle");
  });

  it("HTTP error surfaces the message via the error field", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((async () =>
      failResponse(500)) as unknown as typeof fetch);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:never");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    let api: ProbeApi | undefined;
    render(
      <Probe
        metric="garch"
        expose={(a) => {
          api = a;
        }}
      />,
    );
    expect(api).toBeDefined();
    if (!api) return;

    await act(async () => {
      await api?.download("json");
    });

    await waitFor(() => {
      expect(screen.getByTestId("state").textContent).toContain(
        "error:HTTP 500 on /export/chart/garch?format=json",
      );
    });
  });

  it("notebook format hits the /export/notebook query route", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((async () =>
        okBlob("{}", "application/json")) as unknown as typeof fetch);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:nb");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    let api: ProbeApi | undefined;
    render(
      <Probe
        metric="training_curves"
        expose={(a) => {
          api = a;
        }}
      />,
    );
    expect(api).toBeDefined();
    if (!api) return;

    await act(async () => {
      await api?.download("notebook");
    });

    const call = fetchSpy.mock.calls[0];
    expect(call).toBeDefined();
    expect(call?.[0]).toBe("/export/notebook?metric=training_curves");
  });
});
