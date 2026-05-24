// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import { ACHIEVEMENT_DEFS, deriveUnlocked, TOTAL_TILES_FOR_COMPLETION } from "../achievementDefs";
import { ACHIEVEMENTS_STORAGE_KEY, useAchievementsStore } from "../achievements";

function resetStore() {
  window.localStorage.removeItem(ACHIEVEMENTS_STORAGE_KEY);
  useAchievementsStore.getState().reset();
}

describe("achievements store", () => {
  beforeEach(() => {
    resetStore();
  });

  it("starts with empty progress", () => {
    const s = useAchievementsStore.getState();
    expect(s.tilesOpened.size).toBe(0);
    expect(s.scenariosCompleted.size).toBe(0);
    expect(s.ctfChallengesSolved.size).toBe(0);
    expect(s.labTriggers).toBe(0);
    expect(s.unlocked.size).toBe(0);
  });

  it("opening one tile satisfies the 'first_tile' predicate", () => {
    useAchievementsStore.getState().markTileOpened("trajectory_mean");
    const s = useAchievementsStore.getState();
    expect(s.tilesOpened.has("trajectory_mean")).toBe(true);
    const unlocked = deriveUnlocked(s);
    expect(unlocked.has("first_tile")).toBe(true);
    expect(unlocked.has("explorer")).toBe(false);
  });

  it("opening 25 distinct tiles satisfies the 'explorer' predicate", () => {
    const { markTileOpened } = useAchievementsStore.getState();
    for (let i = 0; i < 25; i++) markTileOpened(`tile_${i}`);
    const s = useAchievementsStore.getState();
    expect(s.tilesOpened.size).toBe(25);
    const unlocked = deriveUnlocked(s);
    expect(unlocked.has("explorer")).toBe(true);
    expect(unlocked.has("first_tile")).toBe(true);
  });

  it("opening TOTAL_TILES tiles satisfies the 'completionist' predicate", () => {
    const { markTileOpened } = useAchievementsStore.getState();
    for (let i = 0; i < TOTAL_TILES_FOR_COMPLETION; i++) markTileOpened(`tile_${i}`);
    const unlocked = deriveUnlocked(useAchievementsStore.getState());
    expect(unlocked.has("completionist")).toBe(true);
  });

  it("re-marking the same id is idempotent", () => {
    useAchievementsStore.getState().markTileOpened("dup");
    useAchievementsStore.getState().markTileOpened("dup");
    useAchievementsStore.getState().markTileOpened("dup");
    expect(useAchievementsStore.getState().tilesOpened.size).toBe(1);
  });

  it("scenario + flag + lab + speed counters drive their respective predicates", () => {
    const api = useAchievementsStore.getState();
    api.markScenarioCompleted("scenario_a");
    api.markCtfSolved("challenge_dp");
    api.incrementLabTriggers();
    api.markSpeedUsed("1");
    let s = useAchievementsStore.getState();
    expect(deriveUnlocked(s).has("first_scenario")).toBe(true);
    expect(deriveUnlocked(s).has("first_flag")).toBe(true);
    expect(deriveUnlocked(s).has("lab_rat")).toBe(false);
    expect(deriveUnlocked(s).has("speed_demon")).toBe(false);

    for (let i = 0; i < 9; i++) api.incrementLabTriggers();
    for (const hz of ["1", "2", "5", "10", "0.5"]) api.markSpeedUsed(hz);
    s = useAchievementsStore.getState();
    expect(deriveUnlocked(s).has("lab_rat")).toBe(true);
    expect(deriveUnlocked(s).has("speed_demon")).toBe(true);
  });

  it("persists mutations to localStorage on every change", () => {
    useAchievementsStore.getState().markTileOpened("traj");
    useAchievementsStore.getState().markCtfSolved("ctf_a");
    const raw = window.localStorage.getItem(ACHIEVEMENTS_STORAGE_KEY);
    expect(raw).not.toBeNull();
    if (raw === null) return;
    const parsed = JSON.parse(raw) as {
      tilesOpened: string[];
      ctfChallengesSolved: string[];
    };
    expect(parsed.tilesOpened).toContain("traj");
    expect(parsed.ctfChallengesSolved).toContain("ctf_a");
  });

  it("recordUnlock writes the id + timestamp", () => {
    useAchievementsStore.getState().recordUnlock("first_tile", 12345);
    const s = useAchievementsStore.getState();
    expect(s.unlocked.has("first_tile")).toBe(true);
    expect(s.unlockTimes.first_tile).toBe(12345);
  });

  it("ACHIEVEMENT_DEFS covers exactly the documented 8+ achievements", () => {
    expect(ACHIEVEMENT_DEFS.length).toBeGreaterThanOrEqual(8);
    const ids = new Set(ACHIEVEMENT_DEFS.map((d) => d.id));
    for (const expected of [
      "first_tile",
      "explorer",
      "completionist",
      "first_scenario",
      "scenario_master",
      "first_flag",
      "ctf_master",
      "lab_rat",
      "speed_demon",
    ]) {
      expect(ids.has(expected)).toBe(true);
    }
  });
});
