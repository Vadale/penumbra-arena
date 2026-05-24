// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ExportButtons } from "../_shared/ExportButtons";

beforeAll(() => {
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

afterEach(() => {
  vi.restoreAllMocks();
});

function deferredOkBlob(): {
  response: Promise<Response>;
  resolve: () => void;
} {
  let resolveFn: () => void = () => {};
  const response = new Promise<Response>((resolve) => {
    resolveFn = () =>
      resolve({
        ok: true,
        status: 200,
        blob: async () => new Blob(["x"], { type: "text/csv" }),
      } as unknown as Response);
  });
  return { response, resolve: resolveFn };
}

describe("ExportButtons", () => {
  it("renders all four format buttons", () => {
    render(<ExportButtons metric="inflation" />);
    expect(screen.getByRole("button", { name: "Export inflation as csv" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export inflation as json" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export inflation as png" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export inflation as ipynb" })).toBeInTheDocument();
  });

  it("clicking csv triggers a fetch to the right URL", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation((async () => ({
      ok: true,
      status: 200,
      blob: async () => new Blob(["a,b\n"], { type: "text/csv" }),
    })) as unknown as typeof fetch);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fake");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<ExportButtons metric="garch" />);
    fireEvent.click(screen.getByRole("button", { name: "Export garch as csv" }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });
    expect(fetchSpy.mock.calls[0]?.[0]).toBe("/export/chart/garch?format=csv");
  });

  it("shows loading state while export is in flight", async () => {
    const { response, resolve } = deferredOkBlob();
    vi.spyOn(globalThis, "fetch").mockImplementation((() => response) as unknown as typeof fetch);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fake");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<ExportButtons metric="wealth" />);
    fireEvent.click(screen.getByRole("button", { name: "Export wealth as json" }));

    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toContain("exporting");
    });

    resolve();

    await waitFor(() => {
      expect(screen.queryByRole("status")).toBeNull();
    });
  });
});
