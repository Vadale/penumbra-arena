/**
 * Educational TFHE (LWE) demo: encrypt bits + homomorphic NOT / XOR.
 *
 * Pedagogical: each ciphertext is an LWE pair (a, b) where b adds
 * scaled plaintext + Gaussian noise. NOT flips a bit homomorphically
 * (single line of arithmetic on the ciphertext). After decryption the
 * round-trip matches the expected boolean.
 */

import { useEffect, useState } from "react";

interface Payload {
  available: boolean;
  algorithm?: string;
  key_dim?: number;
  a_plain?: number;
  b_plain?: number;
  decrypt_a?: number;
  decrypt_b?: number;
  not_a_decrypts_to?: number;
  xor_decrypts_to?: number;
  not_correct?: boolean;
  xor_correct?: boolean;
}

export function TFHEChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch("/crypto/tfhe/demo");
      if (res.ok) setData((await res.json()) as Payload);
    } catch {}
    setBusy(false);
  };

  useEffect(() => {
    void run();
    // biome-ignore lint/correctness/useExhaustiveDependencies: one-shot on mount
  }, []);

  if (!data?.available) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {busy ? "running…" : "TFHE unavailable"}
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "—"} accent />
        <Stat label="LWE dim" value={String(data.key_dim ?? 0)} accent />
        <Stat label="modulus" value="2^32" />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "running…" : "re-run"}
        </button>
      </div>

      <div className="space-y-2">
        <Row op="enc(1) → dec" expected={1} got={data.decrypt_a ?? -1} />
        <Row op="enc(0) → dec" expected={0} got={data.decrypt_b ?? -1} />
        <Row op="NOT(enc(1)) → dec" expected={0} got={data.not_a_decrypts_to ?? -1} highlight />
        <Row
          op="XOR(enc(1), enc(0)) → dec"
          expected={1}
          got={data.xor_decrypts_to ?? -1}
          highlight
        />
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        LWE: ciphertext = (a, b) where a ∈ Z_q^n, b = ⟨a,s⟩ + scale·bit + noise. Homomorphic NOT:
        just (−a, q − b) — gives an LWE encryption of (1 − bit). XOR: addition mod q on both
        components. The noise grows with each op; production TFHE adds bootstrapping to reset it.
      </div>
    </div>
  );
}

function Row({
  op,
  expected,
  got,
  highlight,
}: {
  op: string;
  expected: number;
  got: number;
  highlight?: boolean;
}) {
  const passing = expected === got;
  return (
    <div
      className={
        passing
          ? `border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 ${highlight ? "border-[color:var(--color-penumbra-cyan)]" : ""}`
          : "border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-2 py-1"
      }
    >
      <div className="flex justify-between text-[10px]">
        <span className="text-[color:var(--color-penumbra-muted)]">{op}</span>
        <span
          className={
            passing
              ? "tabular-nums text-[color:var(--color-penumbra-cyan)]"
              : "tabular-nums text-[color:var(--color-penumbra-ember)]"
          }
        >
          got {got} · expected {expected} · {passing ? "✓" : "✗"}
        </span>
      </div>
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
