// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { TOTAL_TILES_FOR_COMPLETION } from "../../stores/achievementDefs";
import { ACHIEVEMENTS_STORAGE_KEY, useAchievementsStore } from "../../stores/achievements";
import { AchievementsPanel } from "../AchievementsPanel";

function resetStore() {
  window.localStorage.removeItem(ACHIEVEMENTS_STORAGE_KEY);
  useAchievementsStore.getState().reset();
}

describe("AchievementsPanel", () => {
  beforeEach(() => {
    resetStore();
  });

  it("renders the progress bar with 0/TOTAL when nothing is opened", () => {
    render(<AchievementsPanel />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "0");
    expect(bar).toHaveAttribute("aria-valuemax", String(TOTAL_TILES_FOR_COMPLETION));
    expect(screen.getByLabelText(/tile discovery progress/i)).toHaveTextContent(
      `0/${TOTAL_TILES_FOR_COMPLETION}`,
    );
  });

  it("progress bar reflects the count of tilesOpened", () => {
    const { markTileOpened } = useAchievementsStore.getState();
    for (let i = 0; i < 12; i++) markTileOpened(`t_${i}`);
    render(<AchievementsPanel />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "12");
    expect(screen.getByLabelText(/tile discovery progress/i)).toHaveTextContent(
      `12/${TOTAL_TILES_FOR_COMPLETION}`,
    );
  });

  it("locked achievements render greyed (opacity-50) and unlocked render bordered cyan", () => {
    const { markTileOpened } = useAchievementsStore.getState();
    markTileOpened("a"); // unlocks 'first_tile' only
    render(<AchievementsPanel />);
    const firstTile = screen.getByLabelText(/achievement Curious unlocked/i);
    expect(firstTile).not.toHaveClass("opacity-50");
    const explorer = screen.getByLabelText(/achievement Explorer locked/i);
    expect(explorer).toHaveClass("opacity-50");
  });

  it("renders all defined achievements", () => {
    render(<AchievementsPanel />);
    // Total counter shows N/N where N = ACHIEVEMENT_DEFS.length.
    // 9 defined in achievementDefs.ts.
    expect(screen.getByText(/all achievements \(0\/9\)/i)).toBeInTheDocument();
  });
});
