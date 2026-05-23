/**
 * Pedersen commitment demo + additive homomorphism.
 *
 * Hiding (the commitment is uniformly random in the group regardless
 * of the committed value), binding (changing the message requires
 * solving discrete log), and homomorphic: C(a) · C(b) = C(a + b).
 */

import { useEffect, useState } from "react";
import { Block, Stat, Verdict } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  message_a?: number;
  message_b?: number;
  commitment_a_short?: string;
  commitment_b_short?: string;
  commitment_sum_short?: string;
  honest_verifies?: boolean;
  tampered_message_verifies?: boolean;
  homomorphic_add_verifies?: boolean;
}

export function PedersenChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch("/crypto/pedersen/demo");
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
        {busy ? "committing…" : "Pedersen unavailable"}
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value="Pedersen / Schnorr-group" accent />
        <Stat label="msg a" value={String(data.message_a ?? 0)} />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "running…" : "re-commit"}
        </button>
      </div>

      <Block label={`C(${data.message_a}) — commitment a`} value={data.commitment_a_short ?? ""} prefix="0x" />
      <Block label={`C(${data.message_b}) — commitment b`} value={data.commitment_b_short ?? ""} prefix="0x" />
      <Block
        label={`C(${data.message_a} + ${data.message_b}) = C(a) · C(b)`}
        value={data.commitment_sum_short ?? ""} prefix="0x"
        accent
      />

      <div className="grid grid-cols-3 gap-2">
        <Verdict
          label="honest open"
          ok={data.honest_verifies ?? false}
          caption="committer reveals (m, r)"
        />
        <Verdict
          label="tampered m"
          ok={data.tampered_message_verifies ?? true}
          inverted
          caption="open with wrong m → reject"
        />
        <Verdict
          label="homomorphic add"
          ok={data.homomorphic_add_verifies ?? false}
          caption="C(a)·C(b) opens to (a+b, r_a+r_b)"
        />
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        C(m, r) = g^m · h^r mod p. Hiding because h^r is uniformly random given r ∈ Z_q. Binding
        because finding (m', r') s.t. g^m · h^r = g^m' · h^r' requires the discrete log of h base g.
      </div>
    </div>
  );
}

// Stat, Verdict, Block now imported from ./_shared
