/**
 * BLS aggregate signature inspector.
 *
 * Pick the most recent block, fetch its aggregate, show signers +
 * verification status. Pedagogically: N individual sigs collapse to
 * ONE 96-byte aggregate point — that's why BLS scales.
 */

import { useFetchJsonOnce, useFetchJsonPoll } from "../hooks/useFetchJson";
import { FetchError, Stat, Verdict } from "./_shared";

interface BLSPayload {
  block_hash: string;
  block_height: number;
  n_signers: number;
  aggregate_short: string;
  signers: string[];
  verified: boolean;
}

interface LatestBlocks {
  blocks?: { hash: string; height: number }[];
}

export function BLSChart() {
  const latestState = useFetchJsonPoll<LatestBlocks>("/chain/latest", 4000);
  const latest =
    latestState.kind === "data"
      ? latestState.value
      : latestState.kind === "error"
        ? latestState.lastValue
        : undefined;
  const blocks = latest?.blocks ?? [];
  const head = blocks.length > 0 ? blocks[blocks.length - 1] : undefined;
  const blockHash = head?.hash;
  const blsState = useFetchJsonOnce<BLSPayload>(blockHash ? `/chain/bls/${blockHash}` : "", {
    enabled: Boolean(blockHash),
  });
  const data = blsState.kind === "data" ? blsState.value : undefined;

  const errorMessage =
    latestState.kind === "error"
      ? latestState.message
      : blsState.kind === "error"
        ? blsState.message
        : null;

  if (!data) {
    if (errorMessage) return <FetchError message={errorMessage} />;
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {blsState.kind === "loading" ? "loading BLS aggregate…" : "no block yet"}
      </div>
    );
  }
  return (
    <div className="font-mono space-y-3">
      {errorMessage && <FetchError message={errorMessage} />}
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
