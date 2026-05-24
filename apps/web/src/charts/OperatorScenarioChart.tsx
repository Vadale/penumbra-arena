/**
 * Phase 6b Tier 5 — Operator Scenario panel.
 *
 * Lists the 12 starter scenarios with a one-click start button per
 * row. When a scenario is active, polls /operator/scenarios/{id}/status
 * once a second and renders a victory / failure checklist + an
 * elapsed-tick counter + a session-scoped mini-leaderboard of
 * (composite-score) values for the scenarios run during this session.
 */

import { useCallback, useEffect, useState } from "react";
import { useAchievementsStore } from "../stores/achievements";
import { FetchError, Stat } from "./_shared";

interface ScenarioSummary {
  id: string;
  title: string;
  difficulty: string;
  description: string;
}

interface ScenariosResponse {
  available: boolean;
  scenarios?: ScenarioSummary[];
  session_scores?: Record<string, number>;
}

interface ProgressPayload {
  scenario_id: string;
  active: boolean;
  victory_met: boolean;
  failure_met: boolean;
  elapsed_ticks?: number;
  progress?: {
    victory?: Record<string, boolean>;
    failure?: Record<string, boolean>;
    operator_coins?: number;
    operator_profit?: number;
    operator_orders_fulfilled?: number;
  };
}

function difficultyAccent(difficulty: string): "ember" | "accent" | "neither" {
  if (difficulty === "hard") return "ember";
  if (difficulty === "open") return "accent";
  return "neither";
}

export function OperatorScenarioChart() {
  const [list, setList] = useState<ScenariosResponse | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [status, setStatus] = useState<ProgressPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const markScenarioCompleted = useAchievementsStore((s) => s.markScenarioCompleted);

  const fetchList = useCallback(async () => {
    try {
      const res = await fetch("/operator/scenarios");
      if (!res.ok) {
        setError(`HTTP ${res.status} on /operator/scenarios`);
        return;
      }
      setList((await res.json()) as ScenariosResponse);
    } catch (exc) {
      setError(`network error: ${exc instanceof Error ? exc.message : String(exc)}`);
    }
  }, []);

  useEffect(() => {
    void fetchList();
  }, [fetchList]);

  useEffect(() => {
    if (activeId === null) {
      setStatus(null);
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(`/operator/scenarios/${activeId}/status`);
        if (!res.ok) {
          if (!cancelled) setError(`HTTP ${res.status} on /operator/scenarios/${activeId}/status`);
          return;
        }
        if (!cancelled) setStatus((await res.json()) as ProgressPayload);
      } catch (exc) {
        if (!cancelled) {
          setError(`network error: ${exc instanceof Error ? exc.message : String(exc)}`);
        }
      }
    };
    void poll();
    const handle = window.setInterval(() => void poll(), 1000);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [activeId]);

  useEffect(() => {
    if (status?.victory_met && status.scenario_id) {
      markScenarioCompleted(status.scenario_id);
    }
  }, [status?.victory_met, status?.scenario_id, markScenarioCompleted]);

  const start = async (id: string) => {
    setError(null);
    try {
      const res = await fetch(`/operator/scenarios/${id}/start`, { method: "POST" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(body.detail ?? `start failed: ${res.status}`);
        return;
      }
      setActiveId(id);
    } catch (exc) {
      setError(String(exc));
    }
  };

  const abandon = async () => {
    if (activeId === null) return;
    try {
      await fetch(`/operator/scenarios/${activeId}/abandon`, { method: "POST" });
    } catch {
      // ignore
    }
    setActiveId(null);
    setStatus(null);
  };

  if (!list?.available || !list.scenarios) {
    if (error) return <FetchError message={error} />;
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        scenarios unavailable (enable operator first via POST /operator/enable)
      </div>
    );
  }

  const sessionScores = list.session_scores ?? {};
  const victory = status?.progress?.victory ?? {};
  const failure = status?.progress?.failure ?? {};

  return (
    <div className="font-mono space-y-3">
      {error && <FetchError message={error} />}
      <div className="grid grid-cols-1 gap-1">
        {list.scenarios.map((s) => {
          const accent = difficultyAccent(s.difficulty);
          const score = sessionScores[s.id];
          const isActive = activeId === s.id;
          return (
            <div
              key={s.id}
              className={`flex items-center justify-between border bg-[color:var(--color-penumbra-bg)] px-2 py-1 ${
                isActive
                  ? "border-[color:var(--color-penumbra-cyan)]"
                  : "border-[color:var(--color-penumbra-border)]"
              }`}
            >
              <div>
                <div className="text-[11px] text-[color:var(--color-penumbra-text)]">{s.title}</div>
                <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
                  {s.id} · {s.difficulty}
                  {score !== undefined ? ` · score ${score.toFixed(2)}` : ""}
                </div>
              </div>
              <button
                type="button"
                onClick={() => void start(s.id)}
                disabled={isActive}
                className={`border px-2 py-0.5 text-[10px] uppercase tracking-wider ${
                  accent === "ember"
                    ? "border-[color:var(--color-penumbra-ember)] text-[color:var(--color-penumbra-ember)]"
                    : "border-[color:var(--color-penumbra-cyan)] text-[color:var(--color-penumbra-cyan)]"
                } disabled:opacity-40`}
              >
                {isActive ? "running" : "start"}
              </button>
            </div>
          );
        })}
      </div>

      {activeId !== null && status !== null && (
        <div className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-bg)] p-2 space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
              {activeId}
            </div>
            <button
              type="button"
              onClick={() => void abandon()}
              className="border border-[color:var(--color-penumbra-ember)] px-2 py-0.5 text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)]"
            >
              abandon
            </button>
          </div>
          <div className="grid grid-cols-3 gap-1">
            <Stat label="ticks" value={status.elapsed_ticks ?? 0} digits={0} accent />
            <Stat
              label="profit"
              value={status.progress?.operator_profit ?? 0}
              digits={2}
              accent={Boolean(status.victory_met)}
              ember={Boolean(status.failure_met)}
            />
            <Stat
              label="orders"
              value={status.progress?.operator_orders_fulfilled ?? 0}
              digits={0}
            />
          </div>
          <div>
            <div className="text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
              victory clauses
            </div>
            {Object.entries(victory).length === 0 ? (
              <div className="text-[9px] text-[color:var(--color-penumbra-muted)]">
                (sandbox — no clauses)
              </div>
            ) : (
              Object.entries(victory).map(([clause, met]) => (
                <div
                  key={clause}
                  className={`text-[10px] ${
                    met
                      ? "text-[color:var(--color-penumbra-cyan)]"
                      : "text-[color:var(--color-penumbra-muted)]"
                  }`}
                >
                  {met ? "[x]" : "[ ]"} {clause}
                </div>
              ))
            )}
          </div>
          <div>
            <div className="text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
              failure clauses
            </div>
            {Object.entries(failure).length === 0 ? (
              <div className="text-[9px] text-[color:var(--color-penumbra-muted)]">
                (sandbox — no clauses)
              </div>
            ) : (
              Object.entries(failure).map(([clause, met]) => (
                <div
                  key={clause}
                  className={`text-[10px] ${
                    met
                      ? "text-[color:var(--color-penumbra-ember)]"
                      : "text-[color:var(--color-penumbra-muted)]"
                  }`}
                >
                  {met ? "[x]" : "[ ]"} {clause}
                </div>
              ))
            )}
          </div>
          <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
            {status.victory_met
              ? "VICTORY — clauses satisfied"
              : status.failure_met
                ? "FAILURE — a clause tripped"
                : "in progress…"}
          </div>
        </div>
      )}

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Scenarios are reproducible from (seed, scenario_id, operator action log). Start a scenario
        to bootstrap its preconditions and emit its opening event.
      </div>
    </div>
  );
}
