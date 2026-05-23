/**
 * Dilithium agent signature inspector.
 *
 * Pick an agent → sign a sample message → verify honest + tampered.
 */

import { useEffect, useState } from "react";

interface Payload {
  available: boolean;
  algorithm?: string;
  agent_id?: number;
  public_key_size?: number;
  secret_key_size?: number;
  signature_size?: number;
  message_size?: number;
  public_key_short?: string;
  signature_short?: string;
  honest_verifies?: boolean;
  tampered_verifies?: boolean;
}

export function DilithiumChart() {
  const [agentId, setAgentId] = useState(0);
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch(`/crypto/dilithium/inspect/${agentId}`);
      if (res.ok) setData((await res.json()) as Payload);
    } catch {}
    setBusy(false);
  };

  useEffect(() => {
    void run();
    // biome-ignore lint/correctness/useExhaustiveDependencies: re-run when agent changes
  }, [agentId]);

  if (!data?.available) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {busy ? "signing…" : "Dilithium unavailable"}
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      <div className="flex items-center gap-2 text-[10px]">
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          agent
        </label>
        <input
          type="number"
          min={0}
          max={49}
          value={agentId}
          onChange={(e) => setAgentId(Math.max(0, Math.min(49, Number(e.target.value))))}
          className="w-16 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
      </div>

      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "—"} accent />
        <Stat label="pubkey" value={`${data.public_key_size ?? 0} B`} accent />
        <Stat label="sk" value={`${data.secret_key_size ?? 0} B`} />
        <Stat label="sig" value={`${data.signature_size ?? 0} B`} accent />
      </div>

      <Block label="public key" value={data.public_key_short ?? ""} />
      <Block label="signature" value={data.signature_short ?? ""} accent />

      <div className="grid grid-cols-2 gap-2">
        <Verdict
          label="honest verify"
          ok={data.honest_verifies ?? false}
          caption="signed by holder of secret"
        />
        <Verdict
          label="tampered message"
          ok={data.tampered_verifies ?? true}
          inverted
          caption="message+'!' must fail"
        />
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        ML-DSA-65 (NIST FIPS 204 / formerly Dilithium-3). Post-quantum signature based on Module-LWE
        + Module-SIS. Penumbra signs every agent move with this — clicking another agent shows their
        unique public key.
      </div>
    </div>
  );
}

function Block({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div
        className={`border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-2 text-[11px] break-all ${accent ? "text-[color:var(--color-penumbra-cyan)]" : "text-[color:var(--color-penumbra-text)]"}`}
      >
        {value}…
      </div>
    </div>
  );
}

function Verdict({
  label,
  ok,
  caption,
  inverted,
}: {
  label: string;
  ok: boolean;
  caption: string;
  inverted?: boolean;
}) {
  const passing = inverted ? !ok : ok;
  return (
    <div
      className={
        passing
          ? "border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] p-2"
          : "border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] p-2"
      }
    >
      <div
        className={
          passing
            ? "text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]"
            : "text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)]"
        }
      >
        {label}: {ok ? "ACCEPT" : "REJECT"}
      </div>
      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">{caption}</div>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div
        className={`tabular-nums ${accent ? "text-[color:var(--color-penumbra-cyan)]" : "text-[color:var(--color-penumbra-text)]"}`}
      >
        {value}
      </div>
    </div>
  );
}
