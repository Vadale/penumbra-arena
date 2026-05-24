// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BranchCompareChart } from "../BranchCompareChart";

const BRANCH_LIST = {
  branches: [
    { branch_id: "exp-0", parent_tick: 100, current_tick: 110, n_agents: 50 },
    { branch_id: "exp-1", parent_tick: 100, current_tick: 115, n_agents: 50 },
    { branch_id: "exp-2", parent_tick: 100, current_tick: 120, n_agents: 50 },
  ],
};

function compareReply(ids: string[]) {
  return {
    branches: ids.map((id, i) => ({
      branch_id: id,
      current_tick: 100 + (i + 1) * 5,
      positions: [0, 1, 2, 3, 4],
      wealth: [10 + i, 20 + i, 30 + i],
      n_agents: 50,
    })),
  };
}

function mockFetch() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : "";
    if (url === "/world/branches") {
      return new Response(JSON.stringify(BRANCH_LIST), { status: 200 });
    }
    if (url === "/world/branches/compare") {
      const body = init?.body ? JSON.parse(String(init.body)) : { branch_ids: [] };
      const ids = (body.branch_ids ?? []) as string[];
      return new Response(JSON.stringify(compareReply(ids)), { status: 200 });
    }
    return new Response("not found", { status: 404 });
  });
}

describe("BranchCompareChart", () => {
  beforeEach(() => {
    mockFetch();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("populates the dropdowns once branches load", async () => {
    render(<BranchCompareChart />);
    await waitFor(() => {
      expect(screen.getByLabelText(/branch A/i)).toBeInTheDocument();
    });
    const selectA = screen.getByLabelText(/branch A/i) as HTMLSelectElement;
    await waitFor(() => {
      expect(selectA.querySelectorAll("option").length).toBeGreaterThan(1);
    });
  });

  it("shows side-by-side charts once two branches are selected", async () => {
    render(<BranchCompareChart />);
    await waitFor(() => {
      expect(screen.getByLabelText(/branch A/i)).toBeInTheDocument();
    });
    const selectA = screen.getByLabelText(/branch A/i) as HTMLSelectElement;
    const selectB = screen.getByLabelText(/branch B/i) as HTMLSelectElement;
    fireEvent.change(selectA, { target: { value: "exp-0" } });
    fireEvent.change(selectB, { target: { value: "exp-1" } });
    await waitFor(() => {
      expect(screen.getAllByText(/A · exp-0/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/B · exp-1/).length).toBeGreaterThan(0);
    });
    // Each of the three metrics renders A and B mini-charts.
    expect(screen.getAllByText(/mean wealth/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/position/i).length).toBeGreaterThan(0);
  });

  it("Swap reverses A and B", async () => {
    render(<BranchCompareChart />);
    await waitFor(() => {
      expect(screen.getByLabelText(/branch A/i)).toBeInTheDocument();
    });
    const selectA = screen.getByLabelText(/branch A/i) as HTMLSelectElement;
    const selectB = screen.getByLabelText(/branch B/i) as HTMLSelectElement;
    fireEvent.change(selectA, { target: { value: "exp-0" } });
    fireEvent.change(selectB, { target: { value: "exp-1" } });
    await waitFor(() => {
      expect(screen.getAllByText(/A · exp-0/).length).toBeGreaterThan(0);
    });
    fireEvent.click(screen.getByLabelText(/swap/i));
    await waitFor(() => {
      expect(screen.getAllByText(/A · exp-1/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/B · exp-0/).length).toBeGreaterThan(0);
    });
  });
});
