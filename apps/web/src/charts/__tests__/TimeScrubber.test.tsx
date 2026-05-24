// @vitest-environment jsdom
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useReplayCursorStore } from "../../stores/replayCursor";
import { useFrameHistoryStore } from "../../streams/frameHistory";
import type { TickFrame } from "../../streams/frames";
import { TimeScrubber } from "../TimeScrubber";

function mkFrame(tick: number): TickFrame {
  return {
    tick,
    match_id: 0,
    match_status: "running",
    agent_positions: { 0: tick % 7 },
    arena_edge_count: 12,
    arena_goals: [0, 3],
  };
}

function seed(n: number): void {
  const frames: TickFrame[] = [];
  for (let i = 0; i < n; i++) frames.push(mkFrame(100 + i));
  useFrameHistoryStore.setState({ frames });
}

describe("TimeScrubber", () => {
  beforeEach(() => {
    useFrameHistoryStore.setState({ frames: [] });
    useReplayCursorStore.setState({ cursor: null, playing: false });
  });

  afterEach(() => {
    vi.useRealTimers();
    useFrameHistoryStore.setState({ frames: [] });
    useReplayCursorStore.setState({ cursor: null, playing: false });
  });

  it("renders waiting state when the history is empty", () => {
    render(<TimeScrubber />);
    expect(screen.getByText(/waiting for frames/i)).toBeInTheDocument();
  });

  it("defaults to the live tick (rightmost)", () => {
    seed(10);
    render(<TimeScrubber />);
    // viewing tick == live tick == 109
    expect(screen.getByText(/tick 109/)).toBeInTheDocument();
    expect(screen.getAllByText("live").length).toBeGreaterThan(0);
    expect(screen.queryByText("replay")).toBeNull();
    const slider = screen.getByRole("slider") as HTMLInputElement;
    expect(slider.value).toBe("9");
  });

  it("dragging the slider sets the viewing tick", () => {
    seed(10);
    render(<TimeScrubber />);
    const slider = screen.getByRole("slider") as HTMLInputElement;
    fireEvent.change(slider, { target: { value: "3" } });
    expect(useReplayCursorStore.getState().cursor).toBe(3);
    expect(screen.getByText(/tick 103/)).toBeInTheDocument();
    expect(screen.getByText("replay")).toBeInTheDocument();
  });

  it("Resume Live clears the cursor", () => {
    seed(10);
    useReplayCursorStore.setState({ cursor: 4 });
    render(<TimeScrubber />);
    fireEvent.click(screen.getByLabelText(/resume live/i));
    expect(useReplayCursorStore.getState().cursor).toBeNull();
  });

  it("Play back advances the cursor over time", () => {
    vi.useFakeTimers();
    seed(10);
    useReplayCursorStore.setState({ cursor: 2 });
    render(<TimeScrubber />);
    fireEvent.click(screen.getByLabelText(/play back/i));
    expect(useReplayCursorStore.getState().playing).toBe(true);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(useReplayCursorStore.getState().cursor).toBe(3);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(useReplayCursorStore.getState().cursor).toBe(4);
  });
});
