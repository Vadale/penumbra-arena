// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TrainingCurves } from "../TrainingCurves";

interface Sample {
  iteration: number;
  actor_loss: number;
  critic_loss: number;
  entropy: number;
  kl: number;
  mean_reward: number;
}

interface Payload {
  available: boolean;
  enabled: boolean;
  iteration: number;
  samples: Sample[];
}

function mockPayload(payload: Payload) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify(payload), { status: 200 })),
    );
}

const sample = (i: number): Sample => ({
  iteration: i,
  actor_loss: 1 - i * 0.05,
  critic_loss: 2 - i * 0.07,
  entropy: 0.8 - i * 0.02,
  kl: 0.01 + i * 0.001,
  mean_reward: i * 0.1,
});

describe("TrainingCurves with brush", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders all four curves when there are >=2 samples", async () => {
    mockPayload({
      available: true,
      enabled: false,
      iteration: 5,
      samples: [sample(0), sample(1), sample(2), sample(3), sample(4)],
    });
    render(<TrainingCurves />);
    await waitFor(() => {
      expect(screen.getByLabelText("actor loss")).toBeInTheDocument();
    });
    expect(screen.getByLabelText("critic loss")).toBeInTheDocument();
    expect(screen.getByLabelText("entropy")).toBeInTheDocument();
    expect(screen.getByLabelText("mean reward (rollout)")).toBeInTheDocument();
    // Brush capture rect is attached to the first curve's SVG.
    expect(screen.getByTestId("brush-capture")).toBeInTheDocument();
    // No window yet -> the hint copy is visible.
    expect(screen.getByText(/drag inside the chart/)).toBeInTheDocument();
  });

  it("renders the start-trainer placeholder when no samples are returned", async () => {
    mockPayload({ available: true, enabled: false, iteration: 0, samples: [] });
    render(<TrainingCurves />);
    await waitFor(() => {
      expect(screen.getByText(/click 'start' to begin training/)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("brush-capture")).toBeNull();
  });
});
