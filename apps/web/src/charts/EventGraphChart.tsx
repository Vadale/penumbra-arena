/**
 * Cross-pillar event graph (Phase 6a Tier 5).
 *
 * Reads /events/stats every 3s and lays out the unique event kinds
 * seen in the recent history as a directed graph. Producers (kinds
 * with emit counts) appear on the left; consumers (kinds whose
 * handler stats show > 0 calls) appear on the right. Edges are the
 * trivial "kind X has Y handlers attached, each ran Z times" line —
 * we don't try to infer cross-kind causality from the bus stats alone.
 *
 * v1: render as a list-grouped layout (kinds in one column, handler
 * counts + p99 next to them). The SVG arrows are tiny — the layout
 * IS the graph.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

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

export function EventGraphChart() {
  const [stats, setStats] = useState<StatsPayload | null>(null);

  useEffect(() => {
    let cancel = false;
    const fetchStats = async () => {
      try {
        const r = await fetch("/events/stats");
        if (r.ok && !cancel) setStats((await r.json()) as StatsPayload);
      } catch {}
    };
    void fetchStats();
    const h = window.setInterval(fetchStats, 3000);
    return () => {
      cancel = true;
      window.clearInterval(h);
    };
  }, []);

  if (!stats) {
    return (
      <div className="font-mono text-[10px] text-[color:var(--color-penumbra-muted)]">
        event graph warming up…
      </div>
    );
  }

  const kinds = Array.from(
    new Set([...Object.keys(stats.emit_counts), ...Object.keys(stats.handler_stats)]),
  ).sort();
  const totalEmits = Object.values(stats.emit_counts).reduce((a, b) => a + b, 0);
  const totalHandlerCalls = Object.values(stats.handler_stats).reduce((a, b) => a + b.n_calls, 0);
  const totalErrors = Object.values(stats.handler_stats).reduce((a, b) => a + b.n_errors, 0);

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="kinds" value={kinds.length} />
        <Stat label="emits" value={totalEmits} accent />
        <Stat label="handler calls" value={totalHandlerCalls} accent />
        <Stat label="errors" value={totalErrors} ember={totalErrors > 0} />
      </div>

      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        Event kinds — producers (emits) → consumers (handler calls · p99 µs)
      </div>

      <div className="space-y-1">
        {kinds.map((kind) => {
          const emits = stats.emit_counts[kind] ?? 0;
          const hs = stats.handler_stats[kind] ?? { n_calls: 0, n_errors: 0, p99_us: 0 };
          const subscribed = hs.n_calls > 0 || kind in stats.handler_stats;
          return (
            <div
              key={kind}
              className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 text-[10px]"
            >
              <div>
                <div className="text-[color:var(--color-penumbra-cyan)]">{kind}</div>
                <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
                  emits: {emits}
                </div>
              </div>
              <svg width="60" height="14" viewBox="0 0 60 14" aria-hidden>
                <title>{`${kind} producer→consumer flow`}</title>
                <line
                  x1="2"
                  y1="7"
                  x2="50"
                  y2="7"
                  stroke={subscribed ? "var(--color-penumbra-cyan)" : "var(--color-penumbra-dim)"}
                  strokeWidth="1"
                />
                <polygon
                  points="50,3 58,7 50,11"
                  fill={subscribed ? "var(--color-penumbra-cyan)" : "var(--color-penumbra-dim)"}
                />
              </svg>
              <div className="text-right">
                <div
                  className={
                    hs.n_errors > 0
                      ? "text-[color:var(--color-penumbra-ember)]"
                      : subscribed
                        ? "text-[color:var(--color-penumbra-text)]"
                        : "text-[color:var(--color-penumbra-dim)]"
                  }
                >
                  {subscribed ? `${hs.n_calls}× · ${hs.p99_us.toFixed(0)} µs` : "no handler"}
                </div>
                {hs.n_errors > 0 ? (
                  <div className="text-[9px] text-[color:var(--color-penumbra-ember)]">
                    {hs.n_errors} err
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
        {kinds.length === 0 && (
          <div className="text-[10px] text-[color:var(--color-penumbra-muted)]">
            no events seen yet
          </div>
        )}
      </div>
    </div>
  );
}
