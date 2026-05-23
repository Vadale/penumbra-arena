/**
 * Groth16 multiplier-circuit verifier.
 *
 * The simplest non-trivial circom circuit: `a * b === c`. A=3, B=5,
 * C=15. The honest proof verifies; bumping c by 1 rejects.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Payload {
  available: boolean;
  reason?: string;
  circuit?: string;
  n_public_inputs?: number;
  honest?: { inputs: number[]; verified: boolean };
  tamper_output?: { inputs: number[]; verified: boolean };
}

export function MultiplierZKChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch("/crypto/zk/multiplier");
      if (res.ok) setData((await res.json()) as Payload);
    } catch {}
    setBusy(false);
  };

  useEffect(() => {
    void run();
  }, []);

  if (!data) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        loading verifier…
      </div>
    );
  }
  if (!data.available) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {data.reason}
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="circuit" value={data.circuit ?? "—"} accent />
        <Stat label="public inputs" value={String(data.n_public_inputs ?? 0)} accent />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "verifying…" : "re-verify"}
        </button>
      </div>

      <Row
        label="honest proof"
        verified={data.honest?.verified ?? false}
        caption={`public inputs = ${JSON.stringify(data.honest?.inputs ?? [])}`}
      />
      <Row
        label="tampered output"
        verified={data.tamper_output?.verified ?? false}
        caption={`public input = ${JSON.stringify(data.tamper_output?.inputs ?? [])} → must reject`}
      />

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        circom circuit:{" "}
        <code>signal input a; signal input b; signal output c; c &lt;== a * b;</code> Witness
        includes a, b; public input is c. Compiled with snarkjs Groth16; verified by our pure-Python
        py_ecc pairing implementation.
      </div>
    </div>
  );
}

function Row({ label, verified, caption }: { label: string; verified: boolean; caption: string }) {
  return (
    <div className="flex items-center justify-between border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-2">
      <div>
        <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
          {label}
        </div>
        <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">{caption}</div>
      </div>
      <div
        className={
          verified
            ? "border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-0.5 text-[11px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]"
            : "border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-2 py-0.5 text-[11px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)]"
        }
      >
        {verified ? "ACCEPT" : "REJECT"}
      </div>
    </div>
  );
}
