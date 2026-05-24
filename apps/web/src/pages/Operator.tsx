/**
 * Operator Console — Phase 6b Tier 2 UI.
 *
 * Drives the `/operator/*` endpoint family (Tier 1) from the browser:
 *  - Polls `GET /operator/status` once a second.
 *  - Lets the user enable / disable the operator slot.
 *  - Submits any of the 20 known action kinds (8 core + 6 attack + 6
 *    defense) via a dropdown-driven form. Each kind ships with a
 *    human label, one-line description, ghost-text placeholders, and a
 *    coarse cost hint sourced from `operator_actions.ts` — the UX fix
 *    for audit finding #5 (no more empty-input HTTP 422s).
 *  - Renders a rolling action log (last 50) with local-time timestamps
 *    and ✓/✗ markers (colour-blind safe).
 *  - Renders the live scorecard with each cell linking to `/bench` for
 *    leaderboard context.
 *
 * No new dependencies: hand-rolled router-friendly page, polling via
 * setInterval, all state local.
 */

import { type ChangeEvent, type FormEvent, useEffect, useMemo, useState } from "react";
import { Stat } from "../charts/_shared";
import {
  ACTION_KINDS,
  ACTION_META,
  type ActionKind,
  coercePayload,
  emptyPayloadFor,
} from "./operator_actions";

interface ActionResult {
  kind: string;
  success: boolean;
  data: Record<string, unknown>;
  error: string | null;
  skipped: boolean;
  elapsed_ms: number;
  applied_tick: number;
}

interface OperatorScore {
  profit: number;
  privacy_preserved: number;
  attacks_survived: number;
  chain_contribution: number;
  composite: number;
}

interface OperatorStatus {
  enabled: boolean;
  hint?: string;
  operator_id?: number;
  position?: number;
  coins?: number;
  inventory?: Record<string, number>;
  epsilon_total?: number;
  epsilon_spent?: number;
  epsilon_remaining?: number;
  queue?: { pending: number; submitted: number; popped: number };
  recent_results?: ActionResult[];
  scorecard?: OperatorScore;
}

interface LogEntry {
  id: number;
  kind: string;
  success: boolean;
  applied_tick: number;
  summary: string;
  /** Local wall-clock at the moment the response was logged (ms since epoch). */
  logged_at: number;
}

const SCENARIO_HINT_KEY = "penumbra.operator.scenario_hint_seen";

const SCORECARD_META: Record<
  keyof OperatorScore,
  { label: string; tooltip: string; digits: number; accent?: boolean }
> = {
  profit: {
    label: "Profit",
    tooltip: "Net coins gained since the slot was enabled (trades + order rewards − costs).",
    digits: 2,
    accent: true,
  },
  privacy_preserved: {
    label: "Privacy Preserved",
    tooltip: "Fraction of ε budget still available — 1.0 means nothing spent.",
    digits: 3,
  },
  attacks_survived: {
    label: "Attacks Survived",
    tooltip: "Count of incoming attack actions the operator's defences rejected.",
    digits: 0,
  },
  chain_contribution: {
    label: "Chain Contribution",
    tooltip: "Blocks proposed or signed by the operator since the slot was enabled.",
    digits: 0,
  },
  composite: {
    label: "Composite Score",
    tooltip: "Weighted blend of profit, privacy, defences, and chain ops (0..1).",
    digits: 3,
    accent: true,
  },
};

function summariseResult(r: ActionResult): string {
  if (r.error) return r.error;
  const bits: string[] = [];
  for (const [k, v] of Object.entries(r.data)) {
    if (typeof v === "number") bits.push(`${k}=${Number.isInteger(v) ? v : v.toFixed(3)}`);
    else if (typeof v === "string" || typeof v === "boolean") bits.push(`${k}=${v}`);
  }
  return bits.length > 0 ? bits.join(" ") : r.success ? "ok" : "fail";
}

function formatLocalTime(ms: number): string {
  const d = new Date(ms);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

interface ResumableSession {
  available: boolean;
  session_id?: string;
  scenario_id?: string;
  scenario_label?: string;
  saved_at_tick?: number;
  saved_at_wall_iso?: string;
}

function readScenarioHintSeen(): boolean {
  try {
    return window.localStorage.getItem(SCENARIO_HINT_KEY) === "1";
  } catch {
    return false;
  }
}

function writeScenarioHintSeen(): void {
  try {
    window.localStorage.setItem(SCENARIO_HINT_KEY, "1");
  } catch {
    // localStorage may be disabled — the hint just won't persist.
  }
}

export function Operator() {
  const [status, setStatus] = useState<OperatorStatus | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [kind, setKind] = useState<ActionKind>("move");
  const [payload, setPayload] = useState<Record<string, string>>(() => emptyPayloadFor("move"));
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [logCounter, setLogCounter] = useState(0);
  const [resumable, setResumable] = useState<ResumableSession | null>(null);
  const [resumeBusy, setResumeBusy] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [scenarioHintDismissed, setScenarioHintDismissed] = useState<boolean>(() =>
    readScenarioHintSeen(),
  );

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch("/operator/status");
        if (!res.ok) return;
        const body = (await res.json()) as OperatorStatus;
        if (!cancelled) setStatus(body);
      } catch {
        // swallow — next tick retries.
      }
    };
    void poll();
    const id = window.setInterval(() => void poll(), 1000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    setPayload(emptyPayloadFor(kind));
  }, [kind]);

  useEffect(() => {
    let cancelled = false;
    const probe = async () => {
      try {
        const res = await fetch("/operator/sessions/resumable");
        if (!res.ok) return;
        const body = (await res.json()) as ResumableSession;
        if (!cancelled) setResumable(body);
      } catch {
        // no banner if the probe fails — next mount can retry
      }
    };
    void probe();
    return () => {
      cancelled = true;
    };
  }, []);

  const onResume = async () => {
    setResumeError(null);
    setResumeBusy(true);
    try {
      const res = await fetch("/operator/sessions/resume", { method: "POST" });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        setResumeError(body.detail ?? `resume failed: ${res.status}`);
        return;
      }
      setResumable({ available: false });
    } catch (exc) {
      setResumeError(exc instanceof Error ? exc.message : "resume failed");
    } finally {
      setResumeBusy(false);
    }
  };

  const onDiscard = async () => {
    setResumeError(null);
    try {
      await fetch("/operator/sessions/discard", { method: "POST" });
    } catch {
      // best-effort: hide the banner regardless so the user is unblocked
    }
    setResumable({ available: false });
  };

  const onField = (field: string) => (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const value = event.target.value;
    setPayload((prev) => ({ ...prev, [field]: value }));
  };

  const appendLog = (result: ActionResult) => {
    setLogCounter((c) => c + 1);
    setLog((prev) => {
      const next: LogEntry = {
        id: logCounter + 1,
        kind: result.kind,
        success: result.success,
        applied_tick: result.applied_tick,
        summary: summariseResult(result),
        logged_at: Date.now(),
      };
      const merged = [next, ...prev];
      return merged.slice(0, 50);
    });
  };

  const postJson = async (path: string, body: unknown): Promise<ActionResult | null> => {
    try {
      const res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
      });
      if (!res.ok) {
        const text = await res.text();
        setSubmitError(`HTTP ${res.status}: ${text.slice(0, 120)}`);
        return null;
      }
      return (await res.json()) as ActionResult;
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "request failed");
      return null;
    }
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    const body = coercePayload(kind, payload);
    const result = await postJson(`/operator/${kind}`, body);
    if (result) appendLog(result);
    setSubmitting(false);
  };

  const onEnable = async () => {
    setSubmitError(null);
    await fetch("/operator/enable", { method: "POST" }).catch(() => null);
  };
  const onDisable = async () => {
    setSubmitError(null);
    await fetch("/operator/disable", { method: "POST" }).catch(() => null);
  };

  const dismissScenarioHint = () => {
    setScenarioHintDismissed(true);
    writeScenarioHintSeen();
  };

  const enabled = status?.enabled ?? false;
  const inventoryText = useMemo(() => {
    const inv = status?.inventory ?? {};
    const entries = Object.entries(inv);
    if (entries.length === 0) return "—";
    return entries.map(([k, v]) => `${k}:${v}`).join(" · ");
  }, [status]);

  const signingStats = useMemo(() => {
    let ok = 0;
    let bad = 0;
    for (const entry of log) {
      if (entry.kind !== "sign" && entry.kind !== "verify") continue;
      if (entry.success) ok += 1;
      else bad += 1;
    }
    return { ok, bad };
  }, [log]);

  const meta = ACTION_META[kind];
  const scorecard = status?.scorecard;

  return (
    <div className="flex h-full flex-col bg-[color:var(--color-penumbra-bg)] text-[color:var(--color-penumbra-text)]">
      <header className="flex items-center justify-between border-b border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] px-4 py-2">
        <div className="flex items-baseline gap-3">
          <a
            href="/"
            className="text-sm font-semibold tracking-tight text-[color:var(--color-penumbra-text)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            penumbra
          </a>
          <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-muted)]">
            operator console
          </span>
        </div>
        <nav className="flex items-center gap-2 text-[11px]">
          {enabled ? (
            <button
              type="button"
              onClick={() => void onDisable()}
              className="rounded-sm border border-[color:var(--color-penumbra-ember)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)] hover:bg-[color:var(--color-penumbra-ember-bg)]"
            >
              disable operator
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void onEnable()}
              className="rounded-sm border border-[color:var(--color-penumbra-cyan)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] hover:bg-[color:var(--color-penumbra-cyan-bg)]"
            >
              enable operator
            </button>
          )}
          <a
            href="/config"
            className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            config
          </a>
          <a
            href="/"
            className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            ← dashboard
          </a>
        </nav>
      </header>

      {resumable?.available && (
        <div
          role="alert"
          aria-label="Resume your last session"
          className="flex items-center justify-between gap-3 border-b border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-4 py-2 font-mono text-[11px] text-[color:var(--color-penumbra-text)]"
        >
          <div className="flex flex-col">
            <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-cyan)]">
              resume your last session
            </span>
            <span>
              {`${resumable.scenario_label ?? resumable.scenario_id ?? "scenario"} — saved at tick ${resumable.saved_at_tick ?? 0}`}
              {resumable.saved_at_wall_iso ? ` (${resumable.saved_at_wall_iso})` : ""}
            </span>
            {resumeError && (
              <span className="text-[10px] text-[color:var(--color-penumbra-ember)]">
                {resumeError}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void onResume()}
              disabled={resumeBusy}
              className="rounded-sm border border-[color:var(--color-penumbra-cyan)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] hover:bg-[color:var(--color-penumbra-cyan-bg)] disabled:opacity-40"
            >
              {resumeBusy ? "resuming…" : "resume"}
            </button>
            <button
              type="button"
              onClick={() => void onDiscard()}
              className="rounded-sm border border-[color:var(--color-penumbra-ember)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)] hover:bg-[color:var(--color-penumbra-ember-bg)]"
            >
              discard
            </button>
          </div>
        </div>
      )}

      {!scenarioHintDismissed && (
        <div
          role="note"
          aria-label="Scenario onboarding hint"
          className="flex items-center justify-between gap-3 border-b border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] px-4 py-2 font-mono text-[11px] text-[color:var(--color-penumbra-muted)]"
        >
          <span>
            New to the cyber range? Start with a guided scenario — open the dashboard and pick the{" "}
            <strong className="text-[color:var(--color-penumbra-text)]">operator scenarios</strong>{" "}
            tile.
          </span>
          <div className="flex items-center gap-2">
            <a
              href="/"
              className="rounded-sm border border-[color:var(--color-penumbra-cyan)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] hover:bg-[color:var(--color-penumbra-cyan-bg)]"
            >
              open scenario list
            </a>
            <button
              type="button"
              onClick={dismissScenarioHint}
              aria-label="Dismiss scenario hint"
              className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-text)]"
            >
              dismiss
            </button>
          </div>
        </div>
      )}

      <main className="grid flex-1 grid-cols-3 gap-3 overflow-hidden p-3 font-mono text-[11px]">
        <section
          aria-label="Operator Status"
          className="col-span-2 flex flex-col gap-2 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] p-3"
        >
          <h2 className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-dim)]">
            operator status
          </h2>
          {!enabled && (
            <div className="text-[color:var(--color-penumbra-muted)]">
              operator is OFF — {status?.hint ?? "press 'enable operator' to bootstrap the slot."}
            </div>
          )}
          {enabled && (
            <div className="grid grid-cols-4 gap-2">
              <Stat label="operator id" value={status?.operator_id ?? 0} accent />
              <Stat label="position" value={status?.position ?? 0} />
              <Stat label="coins" value={status?.coins ?? 0} digits={2} accent />
              <Stat
                label="ε remaining"
                value={status?.epsilon_remaining ?? 0}
                digits={3}
                ember={Boolean(status && (status.epsilon_remaining ?? 0) < 0.1)}
              />
              <Stat
                label="ε spent"
                value={status?.epsilon_spent ?? 0}
                digits={3}
                caption={`/ ${(status?.epsilon_total ?? 0).toFixed(2)}`}
              />
              <Stat label="inventory" value={inventoryText} />
              <Stat
                label="signing ok"
                value={signingStats.ok}
                accent
                caption={`${signingStats.bad} bad`}
              />
              <Stat label="queue pending" value={status?.queue?.pending ?? 0} />
            </div>
          )}
        </section>

        <section
          aria-label="Action Builder"
          className="flex flex-col gap-2 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] p-3"
        >
          <h2 className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-dim)]">
            action builder
          </h2>
          <form className="flex flex-col gap-2" onSubmit={(e) => void onSubmit(e)}>
            <label className="flex flex-col gap-1">
              <span className="text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
                kind
              </span>
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value as ActionKind)}
                className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 text-[11px]"
              >
                {ACTION_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {`${k} — ${ACTION_META[k].label}`}
                  </option>
                ))}
              </select>
            </label>
            <div className="rounded-sm border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 text-[10px] text-[color:var(--color-penumbra-muted)]">
              <div>{meta.description}</div>
              <div className="mt-0.5 text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
                cost: {meta.coins_cost}
              </div>
            </div>
            {Object.keys(payload).map((field) => (
              <label key={field} className="flex flex-col gap-1">
                <span className="text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
                  {field}
                </span>
                <input
                  aria-label={field}
                  type="text"
                  value={payload[field] ?? ""}
                  onChange={onField(field)}
                  placeholder={meta.placeholders[field] ?? ""}
                  className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 text-[11px] text-[color:var(--color-penumbra-text)]"
                />
              </label>
            ))}
            {Object.keys(payload).length === 0 && (
              <div className="text-[10px] text-[color:var(--color-penumbra-muted)]">
                this action takes no parameters
              </div>
            )}
            <button
              type="submit"
              disabled={submitting || !enabled}
              className="mt-1 rounded-sm border border-[color:var(--color-penumbra-cyan)] px-2 py-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] hover:bg-[color:var(--color-penumbra-cyan-bg)] disabled:opacity-40"
            >
              {submitting ? "submitting…" : "submit"}
            </button>
            {submitError && (
              <div className="text-[10px] text-[color:var(--color-penumbra-ember)]">
                {submitError}
              </div>
            )}
          </form>
        </section>

        <section
          aria-label="Action Log"
          className="col-span-3 flex flex-col gap-2 overflow-hidden border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] p-3"
        >
          <h2 className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-dim)]">
            action log (last 50)
          </h2>
          {/* No search/filter: the log is capped at 50 rows so scrolling
              is faster than typing a query. Revisit if we ever uncap it. */}
          <div className="flex-1 overflow-auto">
            <table className="min-w-full text-[11px]">
              <thead>
                <tr className="border-b border-[color:var(--color-penumbra-border)] text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
                  <th className="px-2 py-1 text-left font-normal">time</th>
                  <th className="px-2 py-1 text-left font-normal">tick</th>
                  <th className="px-2 py-1 text-left font-normal">kind</th>
                  <th className="px-2 py-1 text-left font-normal">status</th>
                  <th className="px-2 py-1 text-left font-normal">result</th>
                </tr>
              </thead>
              <tbody>
                {log.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-2 py-2 text-[color:var(--color-penumbra-muted)]">
                      no actions submitted yet
                    </td>
                  </tr>
                )}
                {log.map((entry) => (
                  <tr
                    key={entry.id}
                    className="border-b border-[color:var(--color-penumbra-border)]"
                  >
                    <td className="px-2 py-1 tabular-nums text-[color:var(--color-penumbra-muted)]">
                      {formatLocalTime(entry.logged_at)}
                    </td>
                    <td className="px-2 py-1 tabular-nums text-[color:var(--color-penumbra-cyan)]">
                      {entry.applied_tick}
                    </td>
                    <td className="px-2 py-1">{entry.kind}</td>
                    <td
                      className={
                        entry.success
                          ? "px-2 py-1 text-[color:var(--color-penumbra-cyan)]"
                          : "px-2 py-1 text-[color:var(--color-penumbra-ember)]"
                      }
                    >
                      <span aria-hidden="true">{entry.success ? "✓ " : "✗ "}</span>
                      {entry.success ? "OK" : "FAIL"}
                    </td>
                    <td className="px-2 py-1 text-[color:var(--color-penumbra-muted)]">
                      {entry.summary}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section
          aria-label="Score Card"
          className="col-span-3 flex flex-col gap-2 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] p-3"
        >
          <div className="flex items-baseline justify-between">
            <h2 className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-dim)]">
              score card
            </h2>
            <a
              href="/bench"
              className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] hover:underline"
            >
              compare on /bench →
            </a>
          </div>
          <div className="grid grid-cols-5 gap-2">
            {(Object.keys(SCORECARD_META) as Array<keyof OperatorScore>).map((field) => {
              const cellMeta = SCORECARD_META[field];
              const value = scorecard?.[field] ?? 0;
              return (
                <a
                  key={field}
                  href="/bench"
                  title={`${cellMeta.tooltip} — click to compare on /bench`}
                  aria-label={`${cellMeta.label} (open /bench)`}
                  className="block transition-opacity hover:opacity-80"
                >
                  <Stat
                    label={cellMeta.label}
                    value={value}
                    digits={cellMeta.digits}
                    accent={cellMeta.accent}
                    caption="see /bench →"
                  />
                </a>
              );
            })}
          </div>
        </section>
      </main>
    </div>
  );
}
