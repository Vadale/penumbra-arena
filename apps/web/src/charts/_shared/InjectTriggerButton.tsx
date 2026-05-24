/**
 * Small "Trigger this event" button used inside DetailModal tiles.
 *
 * Concept taught: every wrapped metric whose backend has a paired
 * `/control/inject` event (CPI shock, GARCH spike, slash, agent block)
 * gets the SAME pending → success/error UX by reusing this component.
 * Inline confirmation; no global toast surface to mount.
 */

import { useState } from "react";
import type { InjectionKind } from "../../stores/labHistory";
import { triggerInjection } from "./triggerInjection";

interface Props {
  label: string;
  kind: InjectionKind;
  payload: Record<string, unknown>;
}

export function InjectTriggerButton({ label, kind, payload }: Props) {
  const [pending, setPending] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fire = async () => {
    setPending(true);
    setConfirmation(null);
    setError(null);
    const result = await triggerInjection(kind, payload);
    setPending(false);
    if (result.kind === "ok") {
      setConfirmation(`✓ ${result.record.kind} fired at tick ${result.record.tick}`);
    } else {
      setError(result.message);
    }
  };

  return (
    <div className="flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={() => void fire()}
        disabled={pending}
        className="border border-[color:var(--color-penumbra-cyan)] bg-transparent px-2 py-[2px] font-mono text-[11px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] hover:bg-[color:var(--color-penumbra-cyan)] hover:text-[color:var(--color-penumbra-bg)] disabled:opacity-50"
      >
        {pending ? "firing…" : label}
      </button>
      {confirmation && (
        <div className="font-mono text-[10px] text-[color:var(--color-penumbra-cyan)]">
          {confirmation}
        </div>
      )}
      {error && (
        <div className="font-mono text-[10px] text-[color:var(--color-penumbra-ember)]">
          {error}
        </div>
      )}
    </div>
  );
}

/** Form variant: agent id input + "Block this agent" button. */
export function InjectBlockAgentForm() {
  const [agentId, setAgentId] = useState<number>(0);
  const [reason, setReason] = useState<string>("lab experiment");
  const [pending, setPending] = useState(false);
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fire = async () => {
    setPending(true);
    setConfirmation(null);
    setError(null);
    const result = await triggerInjection("agent.blocked", {
      agent_id: agentId,
      reason,
    });
    setPending(false);
    if (result.kind === "ok") {
      setConfirmation(`✓ agent.blocked fired at tick ${result.record.tick}`);
    } else {
      setError(result.message);
    }
  };

  return (
    <div className="flex flex-col items-start gap-1">
      <div className="flex flex-wrap items-center gap-1">
        <button
          type="button"
          onClick={() => void fire()}
          disabled={pending}
          className="border border-[color:var(--color-penumbra-cyan)] bg-transparent px-2 py-[2px] font-mono text-[11px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] hover:bg-[color:var(--color-penumbra-cyan)] hover:text-[color:var(--color-penumbra-bg)] disabled:opacity-50"
        >
          {pending ? "firing…" : "block this agent"}
        </button>
        <label className="font-mono text-[10px] text-[color:var(--color-penumbra-muted)]">
          id{" "}
          <input
            type="number"
            min={0}
            value={agentId}
            onChange={(e) => setAgentId(Number.parseInt(e.target.value, 10) || 0)}
            className="ml-1 w-14 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 py-[1px] font-mono text-[10px] text-[color:var(--color-penumbra-text)]"
            aria-label="agent id"
          />
        </label>
        <label className="font-mono text-[10px] text-[color:var(--color-penumbra-muted)]">
          reason{" "}
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="ml-1 w-32 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 py-[1px] font-mono text-[10px] text-[color:var(--color-penumbra-text)]"
            aria-label="block reason"
          />
        </label>
      </div>
      {confirmation && (
        <div className="font-mono text-[10px] text-[color:var(--color-penumbra-cyan)]">
          {confirmation}
        </div>
      )}
      {error && (
        <div className="font-mono text-[10px] text-[color:var(--color-penumbra-ember)]">
          {error}
        </div>
      )}
    </div>
  );
}
