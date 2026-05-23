/**
 * BLS aggregate signature inspector.
 *
 * Pick the most recent block, fetch its aggregate, show signers +
 * verification status. Pedagogically: N individual sigs collapse to
 * ONE 96-byte aggregate point — that's why BLS scales.
 */

import { useEffect, useState } from "react";
import { Stat, Verdict } from "./_shared";

interface BLSPayload {
  block_hash: string;
  block_height: number;
  n_signers: number;
  aggregate_short: string;
  signers: string[];
  verified: boolean;
}

export function BLSChart() {
  const [blockHash, setBlockHash] = useState<string | null>(null);
  const [data, setData] = useState<BLSPayload | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const grab = async () => {
      try {
        const res = await fetch("/chain/latest");
        if (!res.ok) return;
        const payload = (await res.json()) as {
          blocks?: { hash: string; height: number }[];
        };
        const blocks = payload.blocks ?? [];
        if (blocks.length === 0) return;
        const head = blocks[blocks.length - 1];
        if (!cancelled && head) setBlockHash(head.hash);
      } catch {}
    };
    void grab();
    const t = window.setInterval(grab, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  useEffect(() => {
    if (!blockHash) return;
    let cancelled = false;
    setLoading(true);
    const grab = async () => {
      try {
        const res = await fetch(`/chain/bls/${blockHash}`);
        if (!res.ok) return;
        const payload = (await res.json()) as BLSPayload;
        if (!cancelled) setData(payload);
      } catch {}
      setLoading(false);
    };
    void grab();
    return () => {
      cancelled = true;
    };
  }, [blockHash]);

  if (!data) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {loading ? "loading BLS aggregate…" : "no block yet"}
      </div>
    );
  }
  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="block height" value={String(data.block_height)} accent />
        <Stat label="signers" value={String(data.n_signers)} accent />
        <Verdict label="aggregate" ok={data.verified} okWord="OK" rejectWord="FAIL" />
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          BLS aggregate (96-byte G2 point compressed → hex short prefix)
        </div>
        <div className="font-mono text-[11px] text-[color:var(--color-penumbra-cyan)] break-all border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-2">
          {data.aggregate_short}…
        </div>
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          signer BLS pubkeys ({data.signers.length})
        </div>
        <div className="flex flex-wrap gap-1 text-[10px]">
          {data.signers.map((s) => (
            <span
              key={s}
              className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1.5 py-0.5 text-[color:var(--color-penumbra-muted)]"
            >
              {s}…
            </span>
          ))}
        </div>
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        block_hash = {data.block_hash.slice(0, 24)}… · fast_aggregate_verify (same message) on
        BLS12-381 G1/G2.
      </div>
    </div>
  );
}
