/**
 * Kyber (ML-KEM-768) KEM handshake demo.
 *
 * Generates a fresh keypair, encapsulates a shared secret against
 * the public key, decapsulates with the secret key, and demonstrates
 * implicit rejection by tampering one byte of the ciphertext.
 */

import { useEffect, useState } from "react";
import { FetchError } from "./_shared";

interface KyberPayload {
  available: boolean;
  algorithm?: string;
  public_key_size?: number;
  secret_key_size?: number;
  ciphertext_size?: number;
  shared_secret_size?: number;
  public_key_short?: string;
  ciphertext_short?: string;
  shared_secret_short?: string;
  honest_match?: boolean;
  tampered_match?: boolean;
}

export function KyberKEMChart() {
  const [data, setData] = useState<KyberPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const grab = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/crypto/kyber/demo");
      if (!res.ok) {
        setError(`HTTP ${res.status} on /crypto/kyber/demo`);
      } else {
        setData((await res.json()) as KyberPayload);
      }
    } catch (exc) {
      setError(`network error: ${exc instanceof Error ? exc.message : String(exc)}`);
    }
    setBusy(false);
  };

  useEffect(() => {
    void grab();
    // biome-ignore lint/correctness/useExhaustiveDependencies: one-shot on mount
  }, []);

  if (!data?.available) {
    if (error) return <FetchError message={error} />;
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {busy ? "running KEM…" : "Kyber unavailable"}
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      {error && <FetchError message={error} />}
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="algorithm" value={data.algorithm ?? "—"} accent />
        <Stat label="pubkey" value={`${data.public_key_size ?? 0} B`} accent />
        <Stat label="ciphertext" value={`${data.ciphertext_size ?? 0} B`} accent />
        <button
          type="button"
          onClick={grab}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "running…" : "re-run KEM"}
        </button>
      </div>

      <Block
        label="public key (Alice publishes)"
        value={data.public_key_short ?? ""}
        size={data.public_key_size ?? 0}
      />
      <Block
        label="ciphertext (Bob → Alice)"
        value={data.ciphertext_short ?? ""}
        size={data.ciphertext_size ?? 0}
      />
      <Block
        label="shared secret (32 B, derived by BOTH sides)"
        value={data.shared_secret_short ?? ""}
        size={data.shared_secret_size ?? 0}
        accent
      />

      <div className="grid grid-cols-2 gap-2">
        <Verdict
          label="honest decaps"
          ok={data.honest_match ?? false}
          caption="encaps/decaps round-trip should match"
        />
        <Verdict
          label="tampered ct decaps"
          ok={data.tampered_match ?? true}
          inverted
          caption="ML-KEM implicit rejection — should NOT match"
        />
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        ML-KEM-768 (NIST FIPS 203 / formerly Kyber-3). Categoria-3 security level (~AES-192).
        Post-quantum: resists Shor-style attacks because it's based on Module-LWE, not factoring/DL.
      </div>
    </div>
  );
}

function Block({
  label,
  value,
  size,
  accent,
}: {
  label: string;
  value: string;
  size: number;
  accent?: boolean;
}) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-[10px]">
        <span className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          {label}
        </span>
        <span className="tabular-nums text-[color:var(--color-penumbra-muted)]">{size} bytes</span>
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
  // When `inverted` is true, ok=false is the GOOD outcome.
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
        {label}: {ok ? "match" : "no match"}
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
