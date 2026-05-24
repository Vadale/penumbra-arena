/**
 * Schnorr Σ-protocol (Fiat-Shamir).
 *
 * Prover knows witness x s.t. y = g^x. They publish (t, c, s) where
 * t = g^r, c = H(y || t || context), s = r + c·x mod q. Verifier
 * recomputes c and checks g^s ≡ t · y^c.
 */

import { useEffect, useState } from "react";
import { FetchError } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  statement_y_short?: string;
  proof_t_short?: string;
  proof_s_short?: string;
  proof_c_short?: string;
  honest_verifies?: boolean;
  wrong_context_verifies?: boolean;
  tampered_response_verifies?: boolean;
}

export function SchnorrChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/crypto/schnorr/demo");
      if (!res.ok) {
        setError(`HTTP ${res.status} on /crypto/schnorr/demo`);
      } else {
        setData((await res.json()) as Payload);
      }
    } catch (exc) {
      setError(`network error: ${exc instanceof Error ? exc.message : String(exc)}`);
    }
    setBusy(false);
  };

  useEffect(() => {
    void run();
  }, []);

  if (!data?.available) {
    if (error) return <FetchError message={error} />;
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {busy ? "proving…" : "Schnorr unavailable"}
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      {error && <FetchError message={error} />}
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value="Schnorr Σ-protocol" accent />
        <Stat label="hash" value="SHA-256 / Fiat-Shamir" />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "running…" : "re-prove"}
        </button>
      </div>

      <Block label="statement y = g^x" value={data.statement_y_short ?? ""} accent />
      <Block label="proof commitment t = g^r" value={data.proof_t_short ?? ""} />
      <Block label="proof response s = r + c·x mod q" value={data.proof_s_short ?? ""} />
      <Block label="challenge c = H(y || t || context)" value={data.proof_c_short ?? ""} />

      <div className="grid grid-cols-3 gap-2">
        <Verdict
          label="honest verify"
          ok={data.honest_verifies ?? false}
          caption="g^s ≡ t · y^c (mod p)"
        />
        <Verdict
          label="wrong context"
          ok={data.wrong_context_verifies ?? true}
          inverted
          caption="verifier recomputes c — fails"
        />
        <Verdict
          label="tampered s"
          ok={data.tampered_response_verifies ?? true}
          inverted
          caption="response flipped → pairing fails"
        />
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Knowledge-soundness: from any prover that succeeds with non-negligible probability we can
        EXTRACT x using a rewinding argument (Pointcheval & Stern, 1996). Zero-knowledge: the
        simulator picks (s, c) first then derives t = g^s · y^(−c) — looks identical to a real
        transcript.
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
        0x{value}…
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
