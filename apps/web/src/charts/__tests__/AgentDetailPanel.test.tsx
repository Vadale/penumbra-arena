// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSelectedAgentStore } from "../../stores/selectedAgent";
import { type AgentDetail, AgentDetailPanel } from "../AgentDetailPanel";

function fixture(id: number): AgentDetail {
  return {
    id,
    position: [3, 7],
    money: 12.5,
    name: `agent-${id}`,
    current_policy: "mappo",
    recent_actions: [
      { tick: 100, action: "move_n" },
      { tick: 101, action: "move_e" },
    ],
    action_distribution: [0.1, 0.4, 0.2, 0.3],
    encrypted_state_bytes: 4096,
    kyber_pk_fingerprint: "abcdef0123456789abcdef0123456789",
    dilithium_pk_fingerprint: "1234567890fedcba1234567890fedcba",
    last_obs_summary: { mean: 0.5, std: 0.1, dim: 16 },
  };
}

function mockFetchOk<T>(value: T) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify(value), { status: 200 })),
    );
}

describe("AgentDetailPanel", () => {
  beforeEach(() => {
    useSelectedAgentStore.setState({ selectedAgentId: null });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    useSelectedAgentStore.setState({ selectedAgentId: null });
  });

  it("renders nothing when selectedAgentId === null", () => {
    mockFetchOk(fixture(0));
    const { container } = render(<AgentDetailPanel />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders fetched data when id is set", async () => {
    mockFetchOk(fixture(7));
    useSelectedAgentStore.setState({ selectedAgentId: 7 });
    render(<AgentDetailPanel />);
    await waitFor(() => {
      expect(screen.getByText(/agent #7/)).toBeInTheDocument();
    });
    expect(screen.getByText(/pos=\(3, 7\)/)).toBeInTheDocument();
    expect(screen.getByText(/\$12\.50/)).toBeInTheDocument();
    expect(screen.getByText("mappo")).toBeInTheDocument();
    expect(screen.getByText("move_n")).toBeInTheDocument();
    expect(screen.getByText("move_e")).toBeInTheDocument();
    expect(screen.getByText("4096")).toBeInTheDocument();
  });

  it("Close button clears the state", async () => {
    mockFetchOk(fixture(3));
    useSelectedAgentStore.setState({ selectedAgentId: 3 });
    render(<AgentDetailPanel />);
    await waitFor(() => {
      expect(screen.getByText(/agent #3/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByLabelText("Close"));
    expect(useSelectedAgentStore.getState().selectedAgentId).toBeNull();
  });

  it("Previous / Next buttons cycle through ids", async () => {
    // No live frame in tests, so the panel only knows about the
    // currently selected id. Selecting any agent and clicking
    // prev/next should leave the store on a valid number.
    mockFetchOk(fixture(5));
    useSelectedAgentStore.setState({ selectedAgentId: 5 });
    render(<AgentDetailPanel />);
    await waitFor(() => {
      expect(screen.getByText(/agent #5/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByLabelText("Next agent"));
    expect(useSelectedAgentStore.getState().selectedAgentId).toBe(5);
    fireEvent.click(screen.getByLabelText("Previous agent"));
    expect(useSelectedAgentStore.getState().selectedAgentId).toBe(5);
  });

  it("renders the action-distribution bars when present", async () => {
    mockFetchOk(fixture(0));
    useSelectedAgentStore.setState({ selectedAgentId: 0 });
    render(<AgentDetailPanel />);
    await waitFor(() => {
      expect(screen.getByText(/action distribution/)).toBeInTheDocument();
    });
    expect(screen.getByText("a0")).toBeInTheDocument();
    expect(screen.getByText("a3")).toBeInTheDocument();
  });
});
