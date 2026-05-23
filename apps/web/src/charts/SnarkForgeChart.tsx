/**
 * SNARK forgery attack panel.
 *
 * Attempts to fool the Groth16 verifier WITHOUT a witness. Two
 * forgery vectors: random-bytes (mutate one curve point) and replay
 * with tampered public inputs. Both must reject; the honest proof
 * still accepts. This IS the soundness statement — visually.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  honest_proof_accepted?: boolean;
  random_forge_accepted?: boolean;
  replay_with_tampered_inputs_accepted?: boolean;
}

export function SnarkForgeChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch("/crypto/snark-forge/demo");
      if (res.ok) setData((await res.json()) as Payload);
    } catch {}
    setBusy(false);
  };

  useEffect(() => {
    void run();
  }, []);

  if (!data?.available) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {busy ? "running forgery…" : "snark-forge unavailable"}
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "—"} accent />
        <Stat label="forger has witness?" value="no" ember />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-ember)] disabled:opacity-50"
        >
          {busy ? "forging…" : "re-attempt"}
        </button>
      </div>

      <Row
        label="honest proof (control)"
        accepted={data.honest_proof_accepted ?? false}
        wantAccepted
        caption="reference: must verify"
      />
      <Row
        label="random-bytes forgery"
        accepted={data.random_forge_accepted ?? true}
        caption="flip A_x low bit → off-curve → pairing fails"
      />
      <Row
        label="replay with tampered public inputs"
        accepted={data.replay_with_tampered_inputs_accepted ?? true}
        caption="proofs bind to public inputs → c folds into linear combo"
      />

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Soundness of Groth16: from any forging adversary with non-negligible probability we can
        extract a discrete-log relation in BN254 — a well-believed hard problem. The pairing
        equation e(A, B) = e(α, β) · e(L(x), γ) · e(C, δ) doesn't hold without the witness.
      </div>
    </div>
  );
}

function Row({
  label,
  accepted,
  wantAccepted,
  caption,
}: {
  label: string;
  accepted: boolean;
  wantAccepted?: boolean;
  caption: string;
}) {
  const passing = wantAccepted ? accepted : !accepted;
  return (
    <div
      className={
        passing
          ? "flex items-center justify-between border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] p-2"
          : "flex items-center justify-between border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] p-2"
      }
    >
      <div>
        <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
          {label}
        </div>
        <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">{caption}</div>
      </div>
      <div
        className={
          passing
            ? "text-[11px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]"
            : "text-[11px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)]"
        }
      >
        {accepted ? "ACCEPTED" : "REJECTED"} {passing ? "✓" : "✗"}
      </div>
    </div>
  );
}
