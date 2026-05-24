/**
 * Loopix-style mix-net — N-hop onion routing in-process.
 *
 * Each relay peels exactly one encryption layer and forwards the
 * inner blob. The dashboard observer (the chain explorer in the
 * real arena) sees encrypted hops but cannot link sender → receiver.
 */

import { useEffect, useState } from "react";
import { Stat, Verdict } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  n_relays?: number;
  payload_bytes?: number;
  onion_bytes?: number;
  per_hop_overhead_bytes?: number;
  honest_delivers?: boolean;
  delays_ms?: number[];
  tampered_layer_rejected?: boolean;
  impostor_relay_rejected?: boolean;
}

export function MixNetChart() {
  const [n, setN] = useState(4);
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch(`/crypto/mix-net/demo?n_relays=${n}`);
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
          n relays
        </label>
        <input
          type="number"
          min={2}
          max={8}
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
          {busy ? "routing…" : "re-route"}
        </button>
      </div>

      {data?.available ? (
        <>
          <div className="grid grid-cols-4 gap-2 text-[10px]">
            <Stat label="algorithm" value="Loopix mix" accent />
            <Stat label="hops" value={String(data.n_relays ?? 0)} />
            <Stat label="payload" value={`${data.payload_bytes ?? 0} B`} />
            <Stat
              label="onion size"
              value={`${data.onion_bytes ?? 0} B`}
              accent
              caption={`+${data.per_hop_overhead_bytes ?? 0} B / hop`}
            />
          </div>

          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
              per-hop delays (ms)
            </div>
            <div className="flex flex-wrap gap-1 text-[11px]">
              {(data.delays_ms ?? []).map((d, i) => (
                <span
                  key={`hop-${i}-${d}`}
                  className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 text-[color:var(--color-penumbra-text)]"
                >
                  r{i}: {d} ms
                </span>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <Verdict
              label="honest delivery"
              ok={data.honest_delivers ?? false}
              caption="payload reaches receiver"
            />
            <Verdict
              label="tampered layer"
              ok={data.tampered_layer_rejected ?? false}
              caption="MAC mismatch caught"
            />
            <Verdict
              label="impostor relay"
              ok={data.impostor_relay_rejected ?? false}
              caption="wrong key cannot peel"
            />
          </div>

          <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
            onion_i = E_{"{K_i}"}(next_hop || delay || onion_{"{i+1}"}). Each relay learns its
            predecessor + successor but not the rest. A global adversary cannot link sender →
            receiver as long as one honest relay shuffles its outbound queue.
          </div>
        </>
      ) : (
        <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
          {busy ? "wrapping onion…" : "click re-route"}
        </div>
      )}
    </div>
  );
}
