/**
 * BlockedAgents — Phase 6a Tier 2 (Security ↔ Market / Logistics).
 *
 * Shows the live blocked-agent list together with the historical
 * block-event count and the gated-trade-attempts gauge. Polls
 * /security/blocked-agents every 2s.
 *
 * A row reads:
 *   agent 7 · signing_rejected · until_tick 1820
 *
 * The historical counter never decreases; the live list shrinks as
 * cool-off windows expire and the orchestrator drains its pending
 * unblocks. The gated-trade-attempts gauge reflects every BUY/SELL
 * that was skipped because the originator was blocked at the time.
 */

import { useFetchJsonPoll } from "../hooks/useFetchJson";
import { FetchError, Stat } from "./_shared";

interface BlockedEntry {
  agent_id: number;
  reason: string;
  until_tick: number;
}

interface BlockedPayload {
  blocked: BlockedEntry[];
  history_count: number;
  blocked_trade_attempts: number;
}

export function BlockedAgentsChart() {
  const state = useFetchJsonPoll<BlockedPayload>("/security/blocked-agents", 2000);
  const data =
    state.kind === "data" ? state.value : state.kind === "error" ? state.lastValue : undefined;

  const blocked = data?.blocked ?? [];
  const historyCount = data?.history_count ?? 0;
  const tradeAttempts = data?.blocked_trade_attempts ?? 0;

  return (
    <div className="font-mono space-y-3">
      {state.kind === "error" && <FetchError message={state.message} />}
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="live blocks" value={blocked.length} ember={blocked.length > 0} />
        <Stat label="history count" value={historyCount} accent />
        <Stat label="gated trade attempts" value={tradeAttempts} ember={tradeAttempts > 0} />
      </div>

      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        Currently blocked
      </div>
      {blocked.length === 0 ? (
        <div className="text-[10px] text-[color:var(--color-penumbra-muted)]">
          no agents in active cool-off
        </div>
      ) : (
        <ul className="text-[10px] space-y-1 max-h-48 overflow-auto">
          {blocked.map((row) => (
            <li key={row.agent_id}>
              <span className="text-[color:var(--color-penumbra-ember)]">agent {row.agent_id}</span>{" "}
              <span className="text-[color:var(--color-penumbra-muted)]">·</span>{" "}
              <span className="text-[color:var(--color-penumbra-cyan)]">{row.reason}</span>{" "}
              <span className="text-[color:var(--color-penumbra-muted)]">·</span>{" "}
              <span className="text-[color:var(--color-penumbra-dim)]">
                until_tick {row.until_tick}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
