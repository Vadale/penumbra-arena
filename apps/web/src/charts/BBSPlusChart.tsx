/**
 * BBS+ selective-disclosure credentials.
 *
 * Issuer signs ONCE over a vector of L attributes; holder later
 * proves "I have a valid credential whose attributes at indices I
 * are values V" without revealing the other coordinates.
 */

import { useEffect, useState } from "react";
import { FetchError, Stat, Verdict } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  n_messages?: number;
  disclosed_indices?: number[];
  disclosed_values?: number[];
  all_messages?: number[];
  honest_signature_verifies?: boolean;
  tampered_message_verifies?: boolean;
  disclosure_verifies?: boolean;
  tampered_disclosure_verifies?: boolean;
}

export function BBSPlusChart() {
  const [n, setN] = useState(5);
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/crypto/bbs-plus/demo?n_messages=${n}`);
      if (!res.ok) {
        setError(`HTTP ${res.status} on /crypto/bbs-plus/demo`);
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
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          n attributes
        </label>
        <input
          type="number"
          min={2}
          max={8}
          value={n}
          onChange={(e) => setN(Number(e.target.value))}
          className="w-16 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "issuing…" : "re-issue"}
        </button>
      </div>

      {data?.available ? (
        <>
          <div className="grid grid-cols-3 gap-2 text-[10px]">
            <Stat label="algorithm" value="BBS+ / BLS12-381" accent />
            <Stat label="schema size" value={String(data.n_messages ?? 0)} />
            <Stat
              label="disclosed"
              value={`${(data.disclosed_indices ?? []).length} / ${data.n_messages ?? 0}`}
              accent
            />
          </div>

          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
              full credential (issuer view)
            </div>
            <div className="grid grid-cols-5 gap-1 text-[10px]">
              {(data.all_messages ?? []).map((m, i) => {
                const isDisclosed = (data.disclosed_indices ?? []).includes(i);
                return (
                  <div
                    key={`attr-${i}-${m}`}
                    className={
                      isDisclosed
                        ? "border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-1 py-1 text-center text-[color:var(--color-penumbra-cyan)]"
                        : "border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 py-1 text-center text-[color:var(--color-penumbra-muted)]"
                    }
                    title={isDisclosed ? "disclosed to verifier" : "kept secret"}
                  >
                    <div className="text-[8px]">#{i}</div>
                    <div>{isDisclosed ? m : "···"}</div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Verdict
              label="signature"
              ok={data.honest_signature_verifies ?? false}
              caption="vector signature accepts"
            />
            <Verdict
              label="tampered msg"
              ok={data.tampered_message_verifies ?? true}
              inverted
              caption="any altered attr → reject"
            />
            <Verdict
              label="honest disclosure"
              ok={data.disclosure_verifies ?? false}
              caption="disclosed indices match"
            />
            <Verdict
              label="tampered disclosure"
              ok={data.tampered_disclosure_verifies ?? true}
              inverted
              caption="wrong value at disclosed idx"
            />
          </div>

          <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
            Pairing-verified: e(A, w + g₂·e) = e(g₁ + h₀·s + Σ hᵢ·mᵢ, g₂). The hidden cells (···)
            are still bound by the signature — the holder cannot forge them, only choose what to
            reveal.
          </div>
        </>
      ) : (
        <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
          {busy ? "issuing BBS+ credential…" : "click re-issue"}
        </div>
      )}
    </div>
  );
}
