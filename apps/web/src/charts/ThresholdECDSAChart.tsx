/**
 * GG18-style threshold ECDSA — n parties co-sign one secp256k1 signature.
 *
 * The signature is plain ECDSA on the wire; verifiers see only the
 * joint public key and the (r, s) tuple. The educational variant
 * runs n-of-n with a trusted dealer.
 */

import { useEffect, useState } from "react";
import { Block, Stat, Verdict } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  n_signers?: number;
  threshold?: number;
  joint_public_key_short?: string;
  signature_r_short?: string;
  signature_s_short?: string;
  honest_verifies?: boolean;
  tampered_message_verifies?: boolean;
  tampered_signature_verifies?: boolean;
  signers_used?: number[];
}

export function ThresholdECDSAChart() {
  const [n, setN] = useState(3);
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch(`/crypto/threshold-ecdsa/demo?n=${n}`);
      if (res.ok) setData((await res.json()) as Payload);
    } catch {}
    setBusy(false);
  };

  useEffect(() => {
    void run();
    // biome-ignore lint/correctness/useExhaustiveDependencies: one-shot on mount
  }, []);

  return (
    <div className="font-mono space-y-3">
      <div className="flex items-center gap-2 text-[10px]">
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          n parties
        </label>
        <input
          type="number"
          min={2}
          max={5}
          value={n}
          onChange={(e) => setN(Number(e.target.value))}
          className="w-12 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "co-signing…" : "re-sign"}
        </button>
      </div>

      {data?.available ? (
        <>
          <div className="grid grid-cols-4 gap-2 text-[10px]">
            <Stat label="curve" value="secp256k1" accent />
            <Stat label="n" value={String(data.n_signers ?? 0)} />
            <Stat label="threshold" value={String(data.threshold ?? 0)} accent />
            <Stat
              label="signers"
              value={(data.signers_used ?? []).join(",")}
              caption="full quorum"
            />
          </div>

          <Block label="joint public key Q" value={data.joint_public_key_short ?? ""} prefix="0x" />
          <Block label="signature r" value={data.signature_r_short ?? ""} prefix="0x" accent />
          <Block label="signature s" value={data.signature_s_short ?? ""} prefix="0x" accent />

          <div className="grid grid-cols-3 gap-2">
            <Verdict
              label="honest co-sign"
              ok={data.honest_verifies ?? false}
              caption="ECDSA verifier accepts"
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
            (r, s) is plain ECDSA — a Bitcoin / Ethereum / OpenSSL verifier cannot tell the sig came
            from n parties. GG18 production replaces the dealer with Paillier-MtA + DKG.
          </div>
        </>
      ) : (
        <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
          {busy ? "running threshold ECDSA…" : "click re-sign"}
        </div>
      )}
    </div>
  );
}
