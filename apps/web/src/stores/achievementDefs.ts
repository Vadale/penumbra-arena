/**
 * Achievement definitions — pure data + predicate.
 *
 * Concept taught: separating the achievement RULES from the progress
 * STATE keeps both files boring. Each definition is a tuple (id, name,
 * desc, check) where check is a side-effect-free predicate on a
 * snapshot of AchievementsState. Adding a new achievement = one entry
 * here; no store migration, no UI change beyond a new card appearing.
 *
 * Total tiles for the "completionist" bar is sourced from the
 * AnalyticsPanel grid — bumping it is a constant edit, not a structural
 * one. The number we use here matches the post-Phase 8 ~98-tile count
 * documented in CLAUDE.md (rounded down to 95 to keep the goal
 * achievable as tiles churn during refactors).
 */

import type { AchievementsState } from "./achievements";

/** Total tile count we treat as 100% for the completionist achievement. */
export const TOTAL_TILES_FOR_COMPLETION = 95;

export interface AchievementDef {
  id: string;
  name: string;
  desc: string;
  check: (s: AchievementsState) => boolean;
}

export const ACHIEVEMENT_DEFS: ReadonlyArray<AchievementDef> = [
  {
    id: "first_tile",
    name: "Curious",
    desc: "Open your first tile.",
    check: (s) => s.tilesOpened.size >= 1,
  },
  {
    id: "explorer",
    name: "Explorer",
    desc: "Open 25 different tiles.",
    check: (s) => s.tilesOpened.size >= 25,
  },
  {
    id: "completionist",
    name: "Completionist",
    desc: `Open all ${TOTAL_TILES_FOR_COMPLETION}+ tiles.`,
    check: (s) => s.tilesOpened.size >= TOTAL_TILES_FOR_COMPLETION,
  },
  {
    id: "first_scenario",
    name: "Operator",
    desc: "Complete your first cyber-range scenario.",
    check: (s) => s.scenariosCompleted.size >= 1,
  },
  {
    id: "scenario_master",
    name: "Drillmaster",
    desc: "Complete 5 cyber-range scenarios.",
    check: (s) => s.scenariosCompleted.size >= 5,
  },
  {
    id: "first_flag",
    name: "Capture",
    desc: "Solve your first CTF flag.",
    check: (s) => s.ctfChallengesSolved.size >= 1,
  },
  {
    id: "ctf_master",
    name: "Flagrunner",
    desc: "Solve all 5 CTF challenges.",
    check: (s) => s.ctfChallengesSolved.size >= 5,
  },
  {
    id: "lab_rat",
    name: "Lab Rat",
    desc: "Trigger 10 lab experiments.",
    check: (s) => s.labTriggers >= 10,
  },
  {
    id: "speed_demon",
    name: "Speed Demon",
    desc: "Try all 5 simulation speed settings.",
    check: (s) => s.speedSettingsUsed.size >= 5,
  },
];

/**
 * Pure derivation: given the current state, return the set of unlocked
 * achievement ids. Used by the panel to render and by the auto-unlock
 * effect to detect newly satisfied predicates.
 */
export function deriveUnlocked(state: AchievementsState): ReadonlySet<string> {
  const ids = new Set<string>();
  for (const def of ACHIEVEMENT_DEFS) {
    if (def.check(state)) ids.add(def.id);
  }
  return ids;
}
