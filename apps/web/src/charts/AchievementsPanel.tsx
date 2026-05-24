/**
 * Achievements panel — gamified discovery dashboard.
 *
 * Concept taught: derive UI from state, not the other way around. The
 * panel reads the AchievementsStore (which records progress) and the
 * ACHIEVEMENT_DEFS table (which encodes the rules) and renders a
 * grid. An auto-unlock effect records the first time each predicate
 * fires; the recent-unlocks strip filters by 24h. The toast unlock
 * banner fires either via the Web Notifications API (if the user has
 * opted in) or as an in-app card at the bottom-right.
 */

import { useEffect, useMemo, useState } from "react";
import {
  ACHIEVEMENT_DEFS,
  deriveUnlocked,
  TOTAL_TILES_FOR_COMPLETION,
} from "../stores/achievementDefs";
import { useAchievementsStore } from "../stores/achievements";

const NEW_BADGE_WINDOW_MS = 24 * 60 * 60 * 1000;

export function AchievementsPanel() {
  const state = useAchievementsStore();
  const unlocked = useMemo(() => deriveUnlocked(state), [state]);
  const recordUnlock = useAchievementsStore((s) => s.recordUnlock);

  // Auto-record any newly satisfied predicate. The store de-duplicates
  // per id so this is safe to run on every render.
  useEffect(() => {
    const now = Date.now();
    for (const id of unlocked) {
      if (!state.unlocked.has(id)) {
        recordUnlock(id, now);
      }
    }
  }, [unlocked, state.unlocked, recordUnlock]);

  const tilesProgress = Math.min(state.tilesOpened.size, TOTAL_TILES_FOR_COMPLETION);
  const pct = (tilesProgress / TOTAL_TILES_FOR_COMPLETION) * 100;

  const now = Date.now();
  const recentlyUnlocked = useMemo(
    () =>
      [...unlocked]
        .map((id) => ({ id, at: state.unlockTimes[id] ?? 0 }))
        .filter((u) => u.at > 0 && now - u.at < NEW_BADGE_WINDOW_MS)
        .sort((a, b) => b.at - a.at),
    [unlocked, state.unlockTimes, now],
  );

  return (
    <div className="font-mono space-y-3">
      <div>
        <div className="mb-1 flex items-baseline justify-between text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          <span>tile discovery</span>
          <span
            role="status"
            className="tabular-nums text-[color:var(--color-penumbra-cyan)]"
            aria-label="tile discovery progress"
          >
            {tilesProgress}/{TOTAL_TILES_FOR_COMPLETION}
          </span>
        </div>
        <div
          className="h-2 w-full border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)]"
          role="progressbar"
          aria-valuenow={tilesProgress}
          aria-valuemin={0}
          aria-valuemax={TOTAL_TILES_FOR_COMPLETION}
        >
          <div
            className="h-full bg-[color:var(--color-penumbra-cyan)]"
            style={{ width: `${pct.toFixed(2)}%` }}
          />
        </div>
        <div className="mt-1 grid grid-cols-3 gap-1 text-[9px] text-[color:var(--color-penumbra-dim)]">
          <span>scenarios {state.scenariosCompleted.size}</span>
          <span>flags {state.ctfChallengesSolved.size}/5</span>
          <span>lab fires {state.labTriggers}</span>
        </div>
      </div>

      {recentlyUnlocked.length > 0 && (
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
            recent unlocks
          </div>
          <ul className="space-y-1">
            {recentlyUnlocked.map(({ id }) => {
              const def = ACHIEVEMENT_DEFS.find((d) => d.id === id);
              if (!def) return null;
              return (
                <li
                  key={id}
                  className="flex items-center justify-between border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[11px]"
                >
                  <span className="text-[color:var(--color-penumbra-cyan)]">{def.name}</span>
                  <span className="text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)]">
                    new!
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          all achievements ({unlocked.size}/{ACHIEVEMENT_DEFS.length})
        </div>
        <ul className="grid grid-cols-2 gap-1">
          {ACHIEVEMENT_DEFS.map((def) => {
            const isUnlocked = unlocked.has(def.id);
            return (
              <li
                key={def.id}
                aria-label={`achievement ${def.name} ${isUnlocked ? "unlocked" : "locked"}`}
                className={
                  isUnlocked
                    ? "border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-bg)] px-2 py-1"
                    : "border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 opacity-50"
                }
              >
                <div className="flex items-baseline gap-1">
                  <span
                    aria-hidden="true"
                    className={
                      isUnlocked
                        ? "text-[10px] text-[color:var(--color-penumbra-cyan)]"
                        : "text-[10px] text-[color:var(--color-penumbra-dim)]"
                    }
                  >
                    {isUnlocked ? "★" : "?"}
                  </span>
                  <span
                    className={
                      isUnlocked
                        ? "text-[11px] text-[color:var(--color-penumbra-text)]"
                        : "text-[11px] text-[color:var(--color-penumbra-muted)]"
                    }
                  >
                    {isUnlocked ? def.name : "locked"}
                  </span>
                </div>
                <div
                  className={
                    isUnlocked
                      ? "text-[9px] text-[color:var(--color-penumbra-dim)]"
                      : "text-[9px] text-[color:var(--color-penumbra-dim)]"
                  }
                >
                  {def.desc}
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Progress persists in localStorage under the penumbra.achievements.v1 key. Reset by clearing
        site data.
      </div>
    </div>
  );
}

/**
 * Global toast renderer — mount once from Dashboard. Renders a tiny
 * card at bottom-right whenever a new achievement unlocks; also fires
 * a browser Notification if the user has granted permission. The toast
 * stays for 6 seconds.
 */
export function AchievementToastHost() {
  const state = useAchievementsStore();
  const unlocked = useMemo(() => deriveUnlocked(state), [state]);
  const [activeToast, setActiveToast] = useState<{ id: string; name: string } | null>(null);
  const [seen, setSeen] = useState<ReadonlySet<string>>(() => new Set(state.unlocked));

  useEffect(() => {
    const newlyUnlocked = [...unlocked].filter((id) => !seen.has(id));
    if (newlyUnlocked.length === 0) return;
    const first = newlyUnlocked[0];
    if (first === undefined) return;
    const def = ACHIEVEMENT_DEFS.find((d) => d.id === first);
    if (def) {
      setActiveToast({ id: def.id, name: def.name });
      // Best-effort browser Notification.
      if (
        typeof window !== "undefined" &&
        typeof window.Notification !== "undefined" &&
        window.Notification.permission === "granted"
      ) {
        try {
          new window.Notification(`Achievement unlocked: ${def.name}`, {
            body: def.desc,
            tag: `achievement:${def.id}`,
          });
        } catch {
          // ignore
        }
      }
    }
    setSeen(new Set(unlocked));
  }, [unlocked, seen]);

  useEffect(() => {
    if (activeToast === null) return;
    const handle = window.setTimeout(() => setActiveToast(null), 6000);
    return () => {
      window.clearTimeout(handle);
    };
  }, [activeToast]);

  if (activeToast === null) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-panel)] px-3 py-2 font-mono text-[11px] shadow-2xl"
    >
      <div className="text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)]">
        achievement unlocked
      </div>
      <div className="text-[color:var(--color-penumbra-cyan)]">{activeToast.name}</div>
    </div>
  );
}
