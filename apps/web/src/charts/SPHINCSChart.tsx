/**
 * SPHINCS+ vs Dilithium — size trade-off visualisation.
 *
 * Hash-based PQ signatures (SPHINCS+) rest on hash-collision
 * assumptions only — no lattices, no codes. The cost is signature
 * size: ~17 KB vs ML-DSA-65's ~3.3 KB. The tile makes the
 * trade-off concrete with side-by-side counters + verdict pills.
 */

import { useEffect, useState } from "react";
import { Block, FetchError, Stat, Verdict } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  public_key_bytes?: number;
  signature_bytes?: number;
  dilithium3_public_key_bytes?: number;
  dilithium3_signature_bytes?: number;
  size_ratio_sig_sphincs_vs_dilithium?: number;
  size_ratio_pk_sphincs_vs_dilithium?: number;
  public_key_short?: string;
  signature_short?: string;
  honest_verifies?: boolean;
  tampered_message_verifies?: boolean;
  tampered_signature_verifies?: boolean;
}

export function SPHINCSChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/crypto/sphincs/demo");
      if (!res.ok) {
        setError(`HTTP ${res.status} on /crypto/sphincs/demo`);
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
        {busy ? "signing with SPHINCS+…" : "SPHINCS+ unavailable"}
      </div>
    );
  }

  const sigRatio = data.size_ratio_sig_sphincs_vs_dilithium ?? 0;
  const pkRatio = data.size_ratio_pk_sphincs_vs_dilithium ?? 0;

  return (
    <div className="font-mono space-y-3">
      {error && <FetchError message={error} />}
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value="SPHINCS+-128f" accent />
        <Stat label="security" value="128-bit PQ" />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "signing…" : "re-sign"}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <Stat
          label="SPHINCS+ sig"
          value={`${(data.signature_bytes ?? 0).toLocaleString()} B`}
          ember
          caption={`${sigRatio.toFixed(1)}× larger than ML-DSA-65`}
        />
        <Stat
          label="Dilithium-3 sig"
          value={`${(data.dilithium3_signature_bytes ?? 0).toLocaleString()} B`}
          accent
          caption="lattice-based, smaller"
        />
        <Stat
          label="SPHINCS+ pubkey"
          value={`${data.public_key_bytes ?? 0} B`}
          accent
          caption={`${(pkRatio * 100).toFixed(2)}% of ML-DSA-65 pk`}
        />
        <Stat
          label="Dilithium-3 pubkey"
          value={`${(data.dilithium3_public_key_bytes ?? 0).toLocaleString()} B`}
          caption="bigger pubkey, smaller sig"
        />
      </div>

      <Block label="SPHINCS+ public key" value={data.public_key_short ?? ""} prefix="0x" />
      <Block label="SPHINCS+ signature" value={data.signature_short ?? ""} prefix="0x" accent />

      <div className="grid grid-cols-3 gap-2">
        <Verdict
          label="honest sig"
          ok={data.honest_verifies ?? false}
          caption="hash-based PQ verifies"
        />
        <Verdict
          label="tampered msg"
          ok={data.tampered_message_verifies ?? true}
          inverted
          caption="different msg → reject"
        />
        <Verdict
          label="tampered sig"
          ok={data.tampered_signature_verifies ?? true}
          inverted
          caption="flipped byte → reject"
        />
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Two PQ families on one shelf: ML-DSA (Dilithium) rests on Module-LWE; SPHINCS+ rests on SHA2
        / SHAKE. Diverse assumptions, two independent migration paths.
      </div>
    </div>
  );
}
