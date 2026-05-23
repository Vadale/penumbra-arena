/**
 * EventBus live log + per-kind stats.
 *
 * Phase 6a Tier 1 — visualises that signals PROPAGATE across pillars.
 * Polls /events/recent every 2s and /events/stats every 5s.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface EventEntry {
  kind: string;
  tick: number;
  payload: Record<string, unknown>;
}

interface RecentPayload {
  events: EventEntry[];
}

interface HandlerStat {
  n_calls: number;
  n_errors: number;
  p99_us: number;
}

interface StatsPayload {
  history_size: number;
  emit_counts: Record<string, number>;
  handler_stats: Record<string, HandlerStat>;
  queued_next_tick: number;
}

export function EventBusChart() {
  const [recent, setRecent] = useState<EventEntry[]>([]);
  const [stats, setStats] = useState<StatsPayload | null>(null);

  useEffect(() => {
    let cancel = false;
    const fetchRecent = async () => {
      try {
        const r = await fetch("/events/recent?limit=20");
        if (r.ok && !cancel) {
          const body = (await r.json()) as RecentPayload;
          setRecent(body.events);
        }
      } catch {}
    };
    const fetchStats = async () => {
      try {
        const r = await fetch("/events/stats");
        if (r.ok && !cancel) setStats((await r.json()) as StatsPayload);
      } catch {}
    };
    void fetchRecent();
    void fetchStats();
    const h1 = window.setInterval(fetchRecent, 2000);
    const h2 = window.setInterval(fetchStats, 5000);
    return () => {
      cancel = true;
      window.clearInterval(h1);
      window.clearInterval(h2);
    };
  }, []);

  const totalEmits = stats ? Object.values(stats.emit_counts).reduce((a, b) => a + b, 0) : 0;
  const totalErrors = stats
    ? Object.values(stats.handler_stats).reduce((a, b) => a + b.n_errors, 0)
    : 0;

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="kinds seen" value={stats ? Object.keys(stats.emit_counts).length : 0} />
        <Stat label="total emits" value={totalEmits} accent />
        <Stat label="handler errors" value={totalErrors} ember={totalErrors > 0} />
        <Stat label="queued next tick" value={stats?.queued_next_tick ?? 0} />
      </div>

      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        Per-kind p99 handler latency
      </div>
      <ul className="text-[10px] grid grid-cols-2 gap-x-3 gap-y-1">
        {stats &&
          Object.entries(stats.handler_stats).map(([kind, hs]) => (
            <li
              key={kind}
              className={hs.p99_us > 1000 ? "text-[color:var(--color-penumbra-ember)]" : ""}
            >
              {kind}: {hs.p99_us.toFixed(0)} µs · {hs.n_calls}×
              {hs.n_errors > 0 ? ` · ${hs.n_errors} err` : ""}
            </li>
          ))}
      </ul>

      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        Recent events
      </div>
      <ul className="text-[10px] space-y-1 max-h-48 overflow-auto">
        {recent
          .slice()
          .reverse()
          .map((e, i) => (
            <li key={`${e.tick}-${e.kind}-${i}`}>
              <span className="text-[color:var(--color-penumbra-dim)]">t{e.tick}</span>{" "}
              <span className="text-[color:var(--color-penumbra-cyan)]">{e.kind}</span>{" "}
              <span className="text-[color:var(--color-penumbra-muted)]">
                {JSON.stringify(e.payload).slice(0, 80)}
              </span>
            </li>
          ))}
      </ul>
    </div>
  );
}
