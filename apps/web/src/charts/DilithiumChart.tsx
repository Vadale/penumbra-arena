/**
 * Dilithium agent signature inspector.
 *
 * Pick an agent → sign a sample message → verify honest + tampered.
 */

import { useState } from "react";
import { useFetchJsonOnce } from "../hooks/useFetchJson";
import { Block, FetchError, Stat, Verdict } from "./_shared";

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
  const state = useFetchJsonOnce<Payload>(`/crypto/dilithium/inspect/${agentId}`);
  const data = state.kind === "data" ? state.value : undefined;

  if (!data?.available) {
    if (state.kind === "error") return <FetchError message={state.message} />;
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {state.kind === "loading" ? "signing…" : "Dilithium unavailable"}
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
