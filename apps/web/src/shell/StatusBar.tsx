/**
 * DF-style bottom status bar: one row, monospace, every important
 * runtime metric in a single glance. No animation, no decoration —
 * pure information density.
 */

import { useEffect, useState } from "react";
import type { TickFrame } from "../streams/frames";

interface RuntimeStats {
  chain_height: number;
  active_validators: number;
  total_validators: number;
  dp_epsilon_remaining: number | null;
  dp_epsilon_total: number | null;
  signing_verified: number;
  signing_rejected: number;
  pty_enabled: boolean;
  repl_enabled: boolean;
}

const POLL_MS = 1500;

export function StatusBar({
  lastFrame,
  connected,
}: {
  lastFrame: TickFrame | null;
  connected: boolean;
}) {
  const [stats, setStats] = useState<RuntimeStats | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const [chain, dp, sigs, pty, repl] = await Promise.all([
          fetch("/chain/latest").then((r) => r.json()),
          fetch("/dp/budget").then((r) => r.json()),
          fetch("/agents/signing-stats").then((r) => r.json()),
          fetch("/pty/status").then((r) => r.json()),
          fetch("/repl/status").then((r) => r.json()),
        ]);
        if (cancelled) return;
        setStats({
          chain_height: chain.height ?? 0,
          active_validators: chain.blocks?.at(-1)?.validator_count ?? 0,
          total_validators: chain.blocks?.at(-1)?.validator_count ?? 0,
          dp_epsilon_remaining: dp.enabled ? dp.epsilon_remaining : null,
          dp_epsilon_total: dp.enabled ? dp.epsilon_total : null,
          signing_verified: sigs.verified ?? 0,
          signing_rejected: sigs.rejected ?? 0,
          pty_enabled: pty.enabled ?? false,
          repl_enabled: repl.enabled ?? false,
        });
      } catch {
        // ignore; next poll will retry
      }
    };
    void poll();
    const timer = window.setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <footer className="flex items-center gap-4 border-t border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-4 py-1 text-[11px] text-[color:var(--color-penumbra-muted)]">
      <StatusCell label="tick" value={lastFrame?.tick ?? "—"} accent />
      <StatusCell label="match" value={lastFrame?.match_id ?? "—"} />
      <StatusCell label="status" value={lastFrame?.match_status ?? "—"} />
      <StatusCell label="edges" value={lastFrame?.arena_edge_count ?? "—"} />
      <Divider />
      <StatusCell
        label="chain"
        value={stats ? `#${stats.chain_height}` : "—"}
        accent={!!stats?.chain_height}
      />
      <StatusCell
        label="ε"
        value={
          stats?.dp_epsilon_remaining !== null && stats?.dp_epsilon_remaining !== undefined
            ? `${stats.dp_epsilon_remaining.toFixed(2)}/${(stats.dp_epsilon_total ?? 0).toFixed(0)}`
            : "off"
        }
        ember={
          stats?.dp_epsilon_remaining !== null &&
          stats?.dp_epsilon_remaining !== undefined &&
          stats.dp_epsilon_remaining < 1.0
        }
      />
      <StatusCell
        label="sigs"
        value={stats ? stats.signing_verified.toLocaleString() : "—"}
        ember={(stats?.signing_rejected ?? 0) > 0}
      />
      <Divider />
      <StatusCell
        label="pty"
        value={stats?.pty_enabled ? "on" : "off"}
        accent={stats?.pty_enabled}
      />
      <StatusCell
        label="repl"
        value={stats?.repl_enabled ? "on" : "off"}
        accent={stats?.repl_enabled}
      />
      <div className="ml-auto text-[10px] uppercase tracking-wider">
        {connected ? (
          <span className="text-[color:var(--color-penumbra-cyan)]">linked</span>
        ) : (
          <span className="text-[color:var(--color-penumbra-ember)]">offline</span>
        )}
      </div>
    </footer>
  );
}

function StatusCell({
  label,
  value,
  accent,
  ember,
}: {
  label: string;
  value: string | number;
  accent?: boolean;
  ember?: boolean;
}) {
  const valueClass = ember
    ? "text-[color:var(--color-penumbra-ember)]"
    : accent
      ? "text-[color:var(--color-penumbra-cyan)]"
      : "text-[color:var(--color-penumbra-text)]";
  return (
    <span className="flex items-baseline gap-1">
      <span className="text-[color:var(--color-penumbra-dim)]">{label}</span>
      <span className={`tabular-nums ${valueClass}`}>{value}</span>
    </span>
  );
}

function Divider() {
  return <span className="text-[color:var(--color-penumbra-border)]">│</span>;
}
