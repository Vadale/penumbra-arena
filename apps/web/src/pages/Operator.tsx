/**
 * Operator Console — Phase 6b Tier 2 UI.
 *
 * Drives the `/operator/*` endpoint family (Tier 1) from the browser:
 *  - Polls `GET /operator/status` once a second.
 *  - Lets the user enable / disable the operator slot.
 *  - Submits any of the 8 known action kinds via a dropdown-driven
 *    form (move, buy, sell, dispatch_order, cancel_assignment,
 *    query_dp, sign, verify).
 *  - Renders a rolling action log (last 50) and the live scorecard.
 *
 * No new dependencies: hand-rolled router-friendly page, polling via
 * setInterval, all state local.
 */

import { type ChangeEvent, type FormEvent, useEffect, useMemo, useState } from "react";
import { Stat } from "../charts/_shared";

const ACTION_KINDS = [
  "move",
  "buy",
  "sell",
  "dispatch_order",
  "cancel_assignment",
  "query_dp",
  "sign",
  "verify",
] as const;
type ActionKind = (typeof ACTION_KINDS)[number];

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
}

function summariseResult(r: ActionResult): string {
  if (r.error) return r.error;
  const bits: string[] = [];
  for (const [k, v] of Object.entries(r.data)) {
    if (typeof v === "number") bits.push(`${k}=${Number.isInteger(v) ? v : v.toFixed(3)}`);
    else if (typeof v === "string" || typeof v === "boolean") bits.push(`${k}=${v}`);
  }
  return bits.length > 0 ? bits.join(" ") : r.success ? "ok" : "fail";
}

function emptyPayloadFor(kind: ActionKind): Record<string, string> {
  switch (kind) {
    case "move":
      return { target_node: "" };
    case "buy":
    case "sell":
      return { product: "", qty: "" };
    case "dispatch_order":
      return { city: "", product: "", qty: "", reward: "" };
    case "cancel_assignment":
      return { order_id: "" };
    case "query_dp":
      return { statistic: "mean_coins", epsilon: "0.1" };
    case "sign":
      return { message: "" };
    case "verify":
      return { message: "", sig: "", public_key: "" };
  }
}

function coercePayload(kind: ActionKind, raw: Record<string, string>): Record<string, unknown> {
  const numericKeys: Record<ActionKind, ReadonlyArray<string>> = {
    move: ["target_node"],
    buy: ["product", "qty"],
    sell: ["product", "qty"],
    dispatch_order: ["city", "product", "qty", "reward"],
    cancel_assignment: ["order_id"],
    query_dp: ["epsilon"],
    sign: [],
    verify: [],
  };
  const out: Record<string, unknown> = {};
  const numKeys = new Set(numericKeys[kind]);
  for (const [k, v] of Object.entries(raw)) {
    if (numKeys.has(k)) {
      const n = Number(v);
      out[k] = Number.isFinite(n) ? n : 0;
    } else {
      out[k] = v;
    }
  }
  return out;
}

export function Operator() {
  const [status, setStatus] = useState<OperatorStatus | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [kind, setKind] = useState<ActionKind>("move");
  const [payload, setPayload] = useState<Record<string, string>>(() => emptyPayloadFor("move"));
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [logCounter, setLogCounter] = useState(0);

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
            href="/"
            className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            ← dashboard
          </a>
        </nav>
      </header>

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
                    {k}
                  </option>
                ))}
              </select>
            </label>
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
                  className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 text-[11px] text-[color:var(--color-penumbra-text)]"
                />
              </label>
            ))}
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
          <div className="flex-1 overflow-auto">
            <table className="min-w-full text-[11px]">
              <thead>
                <tr className="border-b border-[color:var(--color-penumbra-border)] text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
                  <th className="px-2 py-1 text-left font-normal">tick</th>
                  <th className="px-2 py-1 text-left font-normal">kind</th>
                  <th className="px-2 py-1 text-left font-normal">status</th>
                  <th className="px-2 py-1 text-left font-normal">result</th>
                </tr>
              </thead>
              <tbody>
                {log.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-2 py-2 text-[color:var(--color-penumbra-muted)]">
                      no actions submitted yet
                    </td>
                  </tr>
                )}
                {log.map((entry) => (
                  <tr
                    key={entry.id}
                    className="border-b border-[color:var(--color-penumbra-border)]"
                  >
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
          <h2 className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-dim)]">
            score card
          </h2>
          <div className="grid grid-cols-5 gap-2">
            <Stat label="profit" value={status?.scorecard?.profit ?? 0} digits={2} accent />
            <Stat
              label="privacy preserved"
              value={status?.scorecard?.privacy_preserved ?? 0}
              digits={3}
            />
            <Stat label="attacks survived" value={status?.scorecard?.attacks_survived ?? 0} />
            <Stat label="chain contribution" value={status?.scorecard?.chain_contribution ?? 0} />
            <Stat label="composite" value={status?.scorecard?.composite ?? 0} digits={3} accent />
          </div>
        </section>
      </main>
    </div>
  );
}
