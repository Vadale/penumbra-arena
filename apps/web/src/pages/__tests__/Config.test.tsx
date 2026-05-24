import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Config } from "../Config";

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

const SAMPLE_CONFIG = {
  n_agents: 50,
  match_max_ticks: 1000,
  tick_hz: 1,
  reward_weights: {
    dispatch_bonus: 1.5,
    dispatch_penalty: -2.0,
    fill_rate_bonus: 0.5,
  },
  defenses: {
    k_anonymity_k: 5,
    dp_epsilon_budget: 4.0,
  },
  pty_enabled: true,
  mappo_loaded: false,
};

describe("Config page", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the 5 mutable fields + 3 restart-required + 2 read-only badges", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((async () =>
      jsonResponse(SAMPLE_CONFIG)) as unknown as typeof fetch);

    render(<Config />);

    // Mutable runtime fields (5) — keyed by aria-label = config key.
    await waitFor(() => {
      expect(screen.getByLabelText("tick_hz")).toBeInTheDocument();
    });
    expect(screen.getByLabelText("reward_weights.dispatch_bonus")).toBeInTheDocument();
    expect(screen.getByLabelText("reward_weights.dispatch_penalty")).toBeInTheDocument();
    expect(screen.getByLabelText("reward_weights.fill_rate_bonus")).toBeInTheDocument();
    expect(screen.getByLabelText("defenses.dp_epsilon_budget")).toBeInTheDocument();

    // Restart-required fields (3).
    expect(screen.getByLabelText("n_agents")).toBeInTheDocument();
    expect(screen.getByLabelText("match_max_ticks")).toBeInTheDocument();
    expect(screen.getByLabelText("defenses.k_anonymity_k")).toBeInTheDocument();

    // Read-only badges (2).
    expect(screen.getByText("pty_enabled")).toBeInTheDocument();
    expect(screen.getByText("mappo_loaded")).toBeInTheDocument();
    expect(screen.getByText("enabled")).toBeInTheDocument();
    expect(screen.getByText("random_walk")).toBeInTheDocument();
  });

  it("POSTs the selected tick_hz value when Apply is clicked", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(((
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url === "/config" && (init === undefined || init.method === undefined)) {
        return Promise.resolve(jsonResponse(SAMPLE_CONFIG));
      }
      if (url === "/config" && init?.method === "POST") {
        return Promise.resolve(jsonResponse({ applied: ["tick_hz"], restart_required: [] }));
      }
      return Promise.resolve(jsonResponse({}));
    }) as unknown as typeof fetch);

    render(<Config />);

    // Pick the "5x" tick_hz button (the slider replacement) then click the
    // first Apply (which belongs to the tick_hz row).
    const tickFieldset = await screen.findByRole("group", { name: "tick_hz" });
    const fiveX = tickFieldset.querySelector("button[aria-pressed]");
    expect(fiveX).toBeTruthy();

    // Click the 5x option.
    const buttons = tickFieldset.querySelectorAll("button");
    const fiveButton = Array.from(buttons).find((b) => b.textContent === "5x");
    expect(fiveButton).toBeTruthy();
    if (fiveButton) fireEvent.click(fiveButton);

    // Click the apply button that lives next to the fieldset.
    const applyButtons = screen.getAllByRole("button", { name: /^apply$/i });
    const firstApply = applyButtons[0];
    expect(firstApply).toBeDefined();
    if (firstApply) fireEvent.click(firstApply);

    await waitFor(() => {
      const postCall = fetchSpy.mock.calls.find(
        ([url, init]) =>
          url === "/config" &&
          typeof init === "object" &&
          init !== null &&
          (init as RequestInit).method === "POST",
      );
      expect(postCall).toBeDefined();
      const body = JSON.parse((postCall?.[1] as RequestInit).body as string);
      expect(body).toEqual({ tick_hz: 5 });
    });
  });

  it("surfaces a restart warning + Copy env line button when POST returns restart_required", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(((
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url === "/config" && (init === undefined || init.method === undefined)) {
        return Promise.resolve(jsonResponse(SAMPLE_CONFIG));
      }
      if (url === "/config" && init?.method === "POST") {
        return Promise.resolve(jsonResponse({ applied: [], restart_required: ["n_agents"] }));
      }
      return Promise.resolve(jsonResponse({}));
    }) as unknown as typeof fetch);

    render(<Config />);

    const nAgentsInput = await screen.findByLabelText("n_agents");
    fireEvent.change(nAgentsInput, { target: { value: "30" } });

    // Find the Apply button that lives in the same row as the n_agents input.
    const row = nAgentsInput.closest("div");
    expect(row).toBeTruthy();
    const applyBtn = row?.querySelector("button");
    expect(applyBtn).toBeTruthy();
    if (applyBtn) fireEvent.click(applyBtn);

    const warning = await screen.findByRole("alert", { name: /restart required for n_agents/i });
    expect(warning).toBeInTheDocument();
    expect(warning.textContent).toContain("PENUMBRA_N_AGENTS=30");
    expect(screen.getByRole("button", { name: /copy env line/i })).toBeInTheDocument();
  });
});
