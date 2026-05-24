/**
 * Achievements store — gamified discovery progress.
 *
 * Concept taught: persistent client-side progress tracking. Achievements
 * are pure functions over the user's exploration footprint (tiles opened,
 * scenarios completed, CTF flags captured, lab triggers fired, speed
 * settings tried). The store persists every mutation to localStorage so
 * the user keeps their badges across sessions; achievement DEFINITIONS
 * live in `achievementDefs.ts` and read from this state. The store
 * itself does not encode the unlock rules — separation of concerns means
 * adding a new achievement requires only an entry in the defs file, not
 * a store schema migration.
 */

import { create } from "zustand";

const STORAGE_KEY = "penumbra.achievements.v1";

export interface AchievementsState {
  tilesOpened: Set<string>;
  scenariosCompleted: Set<string>;
  ctfChallengesSolved: Set<string>;
  speedSettingsUsed: Set<string>;
  labTriggers: number;
  unlocked: Set<string>;
  unlockTimes: Record<string, number>;
  markTileOpened: (id: string) => void;
  markScenarioCompleted: (id: string) => void;
  markCtfSolved: (id: string) => void;
  markSpeedUsed: (id: string) => void;
  incrementLabTriggers: () => void;
  recordUnlock: (id: string, at: number) => void;
  reset: () => void;
}

interface PersistedShape {
  tilesOpened: string[];
  scenariosCompleted: string[];
  ctfChallengesSolved: string[];
  speedSettingsUsed: string[];
  labTriggers: number;
  unlocked: string[];
  unlockTimes: Record<string, number>;
}

function loadPersisted(): PersistedShape {
  const empty: PersistedShape = {
    tilesOpened: [],
    scenariosCompleted: [],
    ctfChallengesSolved: [],
    speedSettingsUsed: [],
    labTriggers: 0,
    unlocked: [],
    unlockTimes: {},
  };
  if (typeof window === "undefined" || typeof window.localStorage === "undefined") {
    return empty;
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return empty;
    const parsed = JSON.parse(raw) as Partial<PersistedShape>;
    return {
      tilesOpened: Array.isArray(parsed.tilesOpened) ? parsed.tilesOpened : [],
      scenariosCompleted: Array.isArray(parsed.scenariosCompleted) ? parsed.scenariosCompleted : [],
      ctfChallengesSolved: Array.isArray(parsed.ctfChallengesSolved)
        ? parsed.ctfChallengesSolved
        : [],
      speedSettingsUsed: Array.isArray(parsed.speedSettingsUsed) ? parsed.speedSettingsUsed : [],
      labTriggers: typeof parsed.labTriggers === "number" ? parsed.labTriggers : 0,
      unlocked: Array.isArray(parsed.unlocked) ? parsed.unlocked : [],
      unlockTimes:
        parsed.unlockTimes && typeof parsed.unlockTimes === "object" ? parsed.unlockTimes : {},
    };
  } catch {
    return empty;
  }
}

function persist(state: AchievementsState): void {
  if (typeof window === "undefined" || typeof window.localStorage === "undefined") return;
  const payload: PersistedShape = {
    tilesOpened: [...state.tilesOpened],
    scenariosCompleted: [...state.scenariosCompleted],
    ctfChallengesSolved: [...state.ctfChallengesSolved],
    speedSettingsUsed: [...state.speedSettingsUsed],
    labTriggers: state.labTriggers,
    unlocked: [...state.unlocked],
    unlockTimes: state.unlockTimes,
  };
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // quota / disabled — silently ignore, badges still work in-memory
  }
}

const initial = loadPersisted();

export const useAchievementsStore = create<AchievementsState>((set, get) => {
  const after = (mutator: (s: AchievementsState) => Partial<AchievementsState>) => {
    set((s) => {
      const patch = mutator(s);
      return patch;
    });
    persist(get());
  };

  const addTo = <
    K extends "tilesOpened" | "scenariosCompleted" | "ctfChallengesSolved" | "speedSettingsUsed",
  >(
    key: K,
    id: string,
  ) => {
    const current = get()[key];
    if (current.has(id)) return;
    const next = new Set(current);
    next.add(id);
    after(() => ({ [key]: next }) as Partial<AchievementsState>);
  };

  return {
    tilesOpened: new Set(initial.tilesOpened),
    scenariosCompleted: new Set(initial.scenariosCompleted),
    ctfChallengesSolved: new Set(initial.ctfChallengesSolved),
    speedSettingsUsed: new Set(initial.speedSettingsUsed),
    labTriggers: initial.labTriggers,
    unlocked: new Set(initial.unlocked),
    unlockTimes: { ...initial.unlockTimes },
    markTileOpened: (id) => addTo("tilesOpened", id),
    markScenarioCompleted: (id) => addTo("scenariosCompleted", id),
    markCtfSolved: (id) => addTo("ctfChallengesSolved", id),
    markSpeedUsed: (id) => addTo("speedSettingsUsed", id),
    incrementLabTriggers: () => after((s) => ({ labTriggers: s.labTriggers + 1 })),
    recordUnlock: (id, at) => {
      const unlocked = get().unlocked;
      if (unlocked.has(id)) return;
      const nextUnlocked = new Set(unlocked);
      nextUnlocked.add(id);
      const nextTimes = { ...get().unlockTimes, [id]: at };
      after(() => ({ unlocked: nextUnlocked, unlockTimes: nextTimes }));
    },
    reset: () => {
      after(() => ({
        tilesOpened: new Set<string>(),
        scenariosCompleted: new Set<string>(),
        ctfChallengesSolved: new Set<string>(),
        speedSettingsUsed: new Set<string>(),
        labTriggers: 0,
        unlocked: new Set<string>(),
        unlockTimes: {},
      }));
    },
  };
});

/** Exported for tests that need to read the storage key directly. */
export const ACHIEVEMENTS_STORAGE_KEY = STORAGE_KEY;
