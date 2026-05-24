/**
 * FROST threshold Schnorr — t-of-n co-sign with on-wire indistinguishability.
 *
 * The signature verifies as plain Schnorr (R, s); the threshold
 * structure is INVISIBLE to the verifier. Tile shows the (n, t)
 * tunable, verdicts for honest + tamper tests, and the truncated
 * group public key + signature components.
 */

import { useEffect, useState } from "react";
import { Block, FetchError, Stat, Verdict } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  n_signers?: number;
  threshold?: number;
  group_public_key_short?: string;
  signature_r_short?: string;
  signature_s_short?: string;
  honest_verifies?: boolean;
  tampered_message_verifies?: boolean;
  tampered_signature_verifies?: boolean;
  signers_used?: number[];
}

export function FROSTChart() {
  const [n, setN] = useState(5);
  const [t, setT] = useState(3);
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/crypto/frost/demo?n=${n}&t=${t}`);
      if (!res.ok) {
        setError(`HTTP ${res.status} on /crypto/frost/demo`);
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
    // biome-ignore lint/correctness/useExhaustiveDependencies: one-shot on mount
  }, []);

  return (
    <div className="font-mono space-y-3">
      {error && <FetchError message={error} />}
      <div className="flex items-center gap-2 text-[10px]">
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">n</label>
        <input
          type="number"
          min={2}
          max={9}
          value={n}
          onChange={(e) => setN(Number(e.target.value))}
          className="w-12 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">t</label>
        <input
          type="number"
          min={2}
          max={9}
          value={t}
          onChange={(e) => setT(Number(e.target.value))}
          className="w-12 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "signing…" : "re-sign"}
        </button>
      </div>

      {data?.available ? (
        <>
          <div className="grid grid-cols-4 gap-2 text-[10px]">
            <Stat label="algorithm" value="FROST" accent />
            <Stat label="n" value={String(data.n_signers ?? 0)} />
            <Stat label="threshold" value={String(data.threshold ?? 0)} accent />
            <Stat
              label="signers used"
              value={(data.signers_used ?? []).join(",")}
              caption="any t-subset works"
            />
          </div>

          <Block label="group public key Y" value={data.group_public_key_short ?? ""} prefix="0x" />
          <Block label="signature R" value={data.signature_r_short ?? ""} prefix="0x" accent />
          <Block label="signature s" value={data.signature_s_short ?? ""} prefix="0x" accent />

          <div className="grid grid-cols-3 gap-2">
            <Verdict
              label="honest sig"
              ok={data.honest_verifies ?? false}
              caption="threshold cosign verifies"
            />
            <Verdict
              label="tampered msg"
              ok={data.tampered_message_verifies ?? true}
              inverted
              caption="different msg → reject"
            />
            <Verdict
              label="tampered s"
              ok={data.tampered_signature_verifies ?? true}
              inverted
              caption="bumped s → reject"
            />
          </div>

          <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
            FROST signs as plain Schnorr: (R, s). On the wire there is no fingerprint of how many
            parties contributed — the threshold structure is invisible to the verifier.
          </div>
        </>
      ) : (
        <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
          {busy ? "running FROST round…" : "click re-sign"}
        </div>
      )}
    </div>
  );
}
