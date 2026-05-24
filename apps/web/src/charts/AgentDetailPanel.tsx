/**
 * Slide-in panel that inspects a single agent.
 *
 * Concept taught: the privacy story of Penumbra means agent state is
 * never visible in plaintext on the wire — what the dashboard CAN show
 * about a specific agent is (a) decrypted aggregate (its current
 * position, money, recent action labels) and (b) a few public
 * fingerprints (Kyber + Dilithium pubkey hashes) you can compare
 * against the blockchain. This panel is the canonical "drill into one
 * agent" surface; arena clicks set the selected id in
 * `stores/selectedAgent.ts` and the panel mounts once at the dashboard
 * root.
 *
 * Layout (top → bottom):
 *   - Header (id / pos / money) + Close (×)
 *   - Prev/Next agent navigation
 *   - Current policy
 *   - Action distribution bar chart (if action_distribution present)
 *   - Recent actions list (last 10 ticks)
 *   - Encrypted-state bytes + Kyber/Dilithium pubkey fingerprints
 *   - Last-observation mini stats (mean / std / dim)
 *
 * Uses `useFetchJsonOnce` so each id change re-fetches; the panel does
 * NOT poll — agent inspection is a one-shot snapshot, not a live tile.
 */

import { useEffect } from "react";
import { useFetchJsonOnce } from "../hooks/useFetchJson";
import { useSelectedAgentStore } from "../stores/selectedAgent";
import { usePenumbraStore } from "../streams/store";
import { FetchError } from "./_shared";

export interface AgentRecentAction {
  tick: number;
  action: string;
}

export interface AgentLastObs {
  mean: number;
  std: number;
  dim: number;
}

export interface AgentDetail {
  id: number;
  position: [number, number];
  money: number;
  name: string;
  current_policy: string;
  recent_actions: AgentRecentAction[];
  action_distribution?: number[];
  encrypted_state_bytes: number;
  kyber_pk_fingerprint: string;
  dilithium_pk_fingerprint: string;
  last_obs_summary: AgentLastObs;
}

function shortHex(s: string, len = 12): string {
  if (s.length <= len) return s;
  return `${s.slice(0, len)}…`;
}

export function AgentDetailPanel() {
  const selectedAgentId = useSelectedAgentStore((s) => s.selectedAgentId);
  const setSelectedAgentId = useSelectedAgentStore((s) => s.setSelectedAgentId);
  const lastFrame = usePenumbraStore((s) => s.lastFrame);

  // Cycle bounds: prefer the live frame's agent set so prev/next match
  // what's actually in the arena. Fall back to {selectedAgentId} so the
  // panel still navigates in unit tests where no WS is connected.
  const agentIds: number[] =
    lastFrame !== null
      ? Object.keys(lastFrame.agent_positions)
          .map((s) => Number(s))
          .sort((a, b) => a - b)
      : selectedAgentId !== null
        ? [selectedAgentId]
        : [];

  const onClose = () => setSelectedAgentId(null);

  // Escape to close — installed only while the panel is open so we
  // don't fight other components for the key.
  useEffect(() => {
    if (selectedAgentId === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedAgentId(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedAgentId, setSelectedAgentId]);

  if (selectedAgentId === null) return null;

  return (
    <AgentDetailPanelInner
      agentId={selectedAgentId}
      agentIds={agentIds}
      onClose={onClose}
      onSelect={setSelectedAgentId}
    />
  );
}

interface InnerProps {
  agentId: number;
  agentIds: number[];
  onClose: () => void;
  onSelect: (id: number) => void;
}

function AgentDetailPanelInner({ agentId, agentIds, onClose, onSelect }: InnerProps) {
  const state = useFetchJsonOnce<AgentDetail>(`/agents/${agentId}`);

  const idx = agentIds.indexOf(agentId);
  const prevId =
    agentIds.length > 0
      ? idx <= 0
        ? (agentIds[agentIds.length - 1] ?? agentId)
        : (agentIds[idx - 1] ?? agentId)
      : agentId;
  const nextId =
    agentIds.length > 0
      ? idx === -1 || idx >= agentIds.length - 1
        ? (agentIds[0] ?? agentId)
        : (agentIds[idx + 1] ?? agentId)
      : agentId;

  return (
    <aside
      role="dialog"
      aria-label={`Agent ${agentId} detail`}
      aria-modal="false"
      className="fixed top-0 right-0 z-40 flex h-full w-[360px] flex-col border-l border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] font-mono text-[color:var(--color-penumbra-text)] shadow-2xl"
    >
      <header className="flex items-start justify-between border-b border-[color:var(--color-penumbra-border)] px-3 py-2">
        <div className="text-[11px]">
          <div className="text-[color:var(--color-penumbra-cyan)]">
            agent #{agentId}
            {state.kind === "data" ? (
              <>
                {" "}
                <span className="text-[color:var(--color-penumbra-muted)]">·</span>{" "}
                <span className="text-[color:var(--color-penumbra-text)]">
                  pos=({state.value.position[0]}, {state.value.position[1]})
                </span>{" "}
                <span className="text-[color:var(--color-penumbra-muted)]">·</span>{" "}
                <span className="text-[color:var(--color-penumbra-text)]">
                  ${state.value.money.toFixed(2)}
                </span>
              </>
            ) : null}
          </div>
          {state.kind === "data" && state.value.name ? (
            <div className="mt-0.5 text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
              {state.value.name}
            </div>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="ml-2 rounded-sm border border-[color:var(--color-penumbra-border)] px-1.5 py-0.5 text-[11px] leading-none text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
        >
          ×
        </button>
      </header>

      <nav className="flex items-center gap-2 border-b border-[color:var(--color-penumbra-border)] px-3 py-1.5 text-[10px]">
        <button
          type="button"
          onClick={() => onSelect(prevId)}
          aria-label="Previous agent"
          className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
        >
          ‹ prev
        </button>
        <span className="text-[color:var(--color-penumbra-dim)]">
          {agentIds.length > 0 ? `${Math.max(0, idx) + 1} / ${agentIds.length}` : "—"}
        </span>
        <button
          type="button"
          onClick={() => onSelect(nextId)}
          aria-label="Next agent"
          className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
        >
          next ›
        </button>
      </nav>

      <div className="flex-1 space-y-3 overflow-y-auto px-3 py-3 text-[11px]">
        {state.kind === "loading" && (
          <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
            loading agent…
          </div>
        )}
        {state.kind === "error" && <FetchError message={state.message} />}
        {state.kind === "data" && <AgentDetailBody detail={state.value} />}
      </div>
    </aside>
  );
}

function AgentDetailBody({ detail }: { detail: AgentDetail }) {
  return (
    <>
      <Section label="current policy">
        <div className="text-[color:var(--color-penumbra-cyan)]">{detail.current_policy}</div>
      </Section>

      {detail.action_distribution && detail.action_distribution.length > 0 ? (
        <Section label="action distribution">
          <ActionDistribution probs={detail.action_distribution} />
        </Section>
      ) : null}

      <Section label="recent actions">
        {detail.recent_actions.length === 0 ? (
          <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
            no actions recorded
          </div>
        ) : (
          <ul className="space-y-0.5">
            {detail.recent_actions.slice(-10).map((a) => (
              <li
                key={`${a.tick}-${a.action}`}
                className="flex justify-between border-b border-[color:var(--color-penumbra-border)] py-0.5 last:border-b-0"
              >
                <span className="text-[color:var(--color-penumbra-muted)]">t={a.tick}</span>
                <span className="text-[color:var(--color-penumbra-text)]">{a.action}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section label="encrypted state">
        <div className="grid grid-cols-2 gap-2">
          <MiniStat label="bytes" value={String(detail.encrypted_state_bytes)} accent />
          <MiniStat label="obs dim" value={String(detail.last_obs_summary.dim)} />
        </div>
        <div className="mt-2 space-y-1">
          <Fingerprint label="kyber pk" value={detail.kyber_pk_fingerprint} />
          <Fingerprint label="dilithium pk" value={detail.dilithium_pk_fingerprint} />
        </div>
      </Section>

      <Section label="last observation">
        <div className="grid grid-cols-3 gap-2">
          <MiniStat label="mean" value={detail.last_obs_summary.mean.toFixed(3)} />
          <MiniStat label="std" value={detail.last_obs_summary.std.toFixed(3)} />
          <MiniStat label="dim" value={String(detail.last_obs_summary.dim)} />
        </div>
      </Section>
    </>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="mb-1 text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      {children}
    </section>
  );
}

function MiniStat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div
        className={`tabular-nums ${
          accent
            ? "text-[color:var(--color-penumbra-cyan)]"
            : "text-[color:var(--color-penumbra-text)]"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function Fingerprint({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-20 shrink-0 text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </span>
      <span className="break-all text-[10px] text-[color:var(--color-penumbra-text)]">
        {shortHex(value, 20)}
      </span>
    </div>
  );
}

function ActionDistribution({ probs }: { probs: number[] }) {
  const max = Math.max(...probs, 1e-9);
  return (
    <div className="space-y-0.5">
      {probs.map((p, i) => {
        const pct = Math.max(0, Math.min(1, p / max)) * 100;
        const key = `action-${i}`;
        return (
          <div key={key} className="flex items-center gap-2 text-[10px]">
            <span className="w-10 shrink-0 text-[color:var(--color-penumbra-muted)]">a{i}</span>
            <div className="relative h-2 flex-1 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)]">
              <div
                className="absolute top-0 left-0 h-full bg-[color:var(--color-penumbra-cyan)]"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="w-10 shrink-0 text-right tabular-nums text-[color:var(--color-penumbra-text)]">
              {p.toFixed(3)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
