/**
 * Phase 6b Tier 6 — Operator cross-session leaderboard.
 *
 * Lists recorded sessions grouped by scenario_id, sorted by final
 * composite (top-N first), and lets the user click a row to expand
 * the per-session detail + a determinism replay diff + a download
 * link for the underlying actions.parquet.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface SessionMeta {
  session_id: string;
  scenario_id: string | null;
  started_at: number;
  closed_at: number | null;
  n_actions: number;
  final_composite: number;
}

interface SessionsResponse {
  available: boolean;
  sessions?: SessionMeta[];
  n?: number;
}

interface ReplayDiff {
  session_id: string;
  scenario_id?: string | null;
  tolerance: number;
  deterministic: boolean;
  deltas: Record<string, number>;
  original: Record<string, number>;
  replayed: Record<string, number>;
  parquet_path?: string;
}

const TOP_N = 10;

function groupByScenario(sessions: SessionMeta[]): Map<string, SessionMeta[]> {
  const buckets = new Map<string, SessionMeta[]>();
  for (const s of sessions) {
    const key = s.scenario_id ?? "(no-scenario)";
    const arr = buckets.get(key) ?? [];
    arr.push(s);
    buckets.set(key, arr);
  }
  for (const arr of buckets.values()) {
    arr.sort((a, b) => b.final_composite - a.final_composite);
  }
  return buckets;
}

export function OperatorLeaderboardChart() {
  const [data, setData] = useState<SessionsResponse | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [replay, setReplay] = useState<ReplayDiff | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Abort an in-flight request when the next poll fires or the
    // component unmounts. Without this, a slow /operator/sessions
    // endpoint accumulates concurrent fetches faster than they resolve
    // and the React tree thrashes setData with stale-then-fresh races.
    let cancelled = false;
    let currentController: AbortController | null = null;

    const poll = async () => {
      currentController?.abort();
      const controller = new AbortController();
      currentController = controller;
      try {
        const res = await fetch("/operator/sessions", { signal: controller.signal });
        if (cancelled || controller.signal.aborted) return;
        if (res.ok) setData((await res.json()) as SessionsResponse);
      } catch (exc) {
        if (cancelled || controller.signal.aborted) return;
        if (exc instanceof DOMException && exc.name === "AbortError") return;
        setError(String(exc));
      }
    };

    void poll();
    const handle = window.setInterval(() => void poll(), 5000);
    return () => {
      cancelled = true;
      currentController?.abort();
      window.clearInterval(handle);
    };
  }, []);

  const expand = async (sessionId: string) => {
    setError(null);
    setReplay(null);
    if (expanded === sessionId) {
      setExpanded(null);
      return;
    }
    setExpanded(sessionId);
    try {
      const res = await fetch(`/operator/sessions/${sessionId}/replay`);
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(body.detail ?? `replay failed: ${res.status}`);
        return;
      }
      setReplay((await res.json()) as ReplayDiff);
    } catch (exc) {
      setError(String(exc));
    }
  };

  if (!data?.available || !data.sessions) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        leaderboard unavailable — no recorded sessions yet (enable operator + run a scenario)
      </div>
    );
  }

  const grouped = groupByScenario(data.sessions);

  return (
    <div className="font-mono space-y-3">
      {error && <div className="text-[10px] text-[color:var(--color-penumbra-ember)]">{error}</div>}
      <div className="text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {data.sessions.length} session{data.sessions.length === 1 ? "" : "s"} on disk · top {TOP_N}{" "}
        per scenario
      </div>
      {Array.from(grouped.entries()).map(([scenarioId, rows]) => (
        <div key={scenarioId} className="space-y-1">
          <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]">
            {scenarioId}
          </div>
          {rows.slice(0, TOP_N).map((row, idx) => {
            const isOpen = expanded === row.session_id;
            return (
              <div
                key={row.session_id}
                className={`border bg-[color:var(--color-penumbra-bg)] ${
                  isOpen
                    ? "border-[color:var(--color-penumbra-cyan)]"
                    : "border-[color:var(--color-penumbra-border)]"
                }`}
              >
                <button
                  type="button"
                  onClick={() => void expand(row.session_id)}
                  className="w-full flex items-center justify-between px-2 py-1 text-left"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] text-[color:var(--color-penumbra-dim)]">
                      #{idx + 1}
                    </span>
                    <span className="text-[10px] text-[color:var(--color-penumbra-text)]">
                      {row.session_id}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-[9px] tabular-nums text-[color:var(--color-penumbra-muted)]">
                    <span>{row.n_actions} actions</span>
                    <span className="text-[color:var(--color-penumbra-text)]">
                      {row.final_composite.toFixed(3)}
                    </span>
                  </div>
                </button>
                {isOpen && (
                  <div className="border-t border-[color:var(--color-penumbra-border)] px-2 py-2 space-y-2">
                    {replay === null ? (
                      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
                        running replay…
                      </div>
                    ) : (
                      <>
                        <div className="grid grid-cols-3 gap-1">
                          <Stat
                            label="composite Δ"
                            value={replay.deltas.composite ?? 0}
                            digits={6}
                            accent={replay.deterministic}
                            ember={!replay.deterministic}
                          />
                          <Stat label="profit Δ" value={replay.deltas.profit ?? 0} digits={4} />
                          <Stat
                            label="privacy Δ"
                            value={replay.deltas.privacy_preserved ?? 0}
                            digits={4}
                          />
                        </div>
                        <div className="text-[9px]">
                          determinism:{" "}
                          <span
                            className={
                              replay.deterministic
                                ? "text-[color:var(--color-penumbra-cyan)]"
                                : "text-[color:var(--color-penumbra-ember)]"
                            }
                          >
                            {replay.deterministic ? "OK" : "DRIFT"}
                          </span>
                          {"  ·  tolerance "}
                          <span className="tabular-nums">{replay.tolerance.toExponential(0)}</span>
                        </div>
                        {replay.parquet_path && (
                          <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
                            parquet:{" "}
                            <code className="text-[color:var(--color-penumbra-muted)]">
                              {replay.parquet_path}
                            </code>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ))}
      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Replay diffs are computed by re-running the recorded action stream against a fresh,
        identically-seeded operator context and comparing the resulting scorecard to the original.
      </div>
    </div>
  );
}
