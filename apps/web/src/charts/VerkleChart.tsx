/**
 * Verkle tree (KZG/BLS12-381) — proof-size compression vs Merkle.
 *
 * A KZG opening is one G1 point (48 bytes) per tree level; a Merkle
 * sibling list grows with depth × hash size. The tile lets the user
 * dial up n_leaves and watch the compression ratio diverge.
 */

import { useEffect, useState } from "react";
import { Stat, Verdict } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  n_leaves?: number;
  merkle_proof_bytes?: number;
  verkle_proof_bytes?: number;
  compression_ratio?: number;
  evaluation_point_z?: number;
  evaluation_y?: number;
  honest_verifies?: boolean;
  tampered_y_verifies?: boolean;
  reason?: string;
}

export function VerkleChart() {
  const [leaves, setLeaves] = useState(1_000_000);
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch(`/crypto/verkle/demo?n_leaves=${leaves}`);
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
          n leaves
        </label>
        <input
          type="number"
          min={1000}
          step={1000}
          value={leaves}
          onChange={(e) => setLeaves(Number(e.target.value))}
          className="w-32 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "computing…" : "re-prove"}
        </button>
      </div>

      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value="KZG / BLS12-381" accent />
        <Stat label="n leaves" value={(data?.n_leaves ?? 0).toLocaleString()} />
        <Stat
          label="compression"
          value={`${(data?.compression_ratio ?? 0).toFixed(2)}×`}
          accent
          caption="Merkle bytes ÷ Verkle bytes"
        />
      </div>

      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <Stat
          label="Merkle proof"
          value={`${(data?.merkle_proof_bytes ?? 0).toLocaleString()} B`}
          ember
          caption="d × 32 bytes (binary)"
        />
        <Stat
          label="Verkle proof"
          value={`${(data?.verkle_proof_bytes ?? 0).toLocaleString()} B`}
          accent
          caption="d × 48 bytes (G1 point)"
        />
      </div>

      {data?.available ? (
        <>
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <Stat label="eval point z" value={String(data.evaluation_point_z ?? 0)} />
            <Stat label="f(z)" value={String(data.evaluation_y ?? 0)} accent />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Verdict
              label="honest open"
              ok={data.honest_verifies ?? false}
              caption="pairing equation accepts"
            />
            <Verdict
              label="tampered y"
              ok={data.tampered_y_verifies ?? true}
              inverted
              caption="bumped y → reject"
            />
          </div>
        </>
      ) : (
        <div className="text-[10px] text-[color:var(--color-penumbra-ember)]">
          {data?.reason ?? "KZG unavailable; showing proof-size estimate only"}
        </div>
      )}

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Verkle proofs replace each Merkle sibling list with ONE KZG opening per level. The constant
        per-level cost compresses dramatically at depth — Ethereum's "Verge" plan banks on it.
      </div>
    </div>
  );
}
