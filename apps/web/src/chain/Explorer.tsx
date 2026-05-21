/**
 * Chain Explorer side panel.
 *
 * Polls /chain/latest at 3 Hz and renders the most recent 5 blocks as
 * a stack of cards. Each card shows the height, hash prefix, proposer
 * prefix, validator count, and a compact list of MatchOutcomes the
 * block sealed.
 */

import type { BlockView } from "../streams/chain";
import { useChainLatest } from "../streams/chain";

function hashPrefix(hex: string, n = 12): string {
  return hex.length > n ? `${hex.slice(0, n)}…` : hex;
}

function BlockCard({ block }: { block: BlockView }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-900/40 p-3">
      <div className="flex items-baseline justify-between">
        <div className="text-sm font-medium">block #{block.height}</div>
        <div className="font-mono text-xs text-slate-400">{hashPrefix(block.hash)}</div>
      </div>
      <div className="mt-1 text-xs text-slate-500">
        proposer <span className="font-mono">{hashPrefix(block.proposer_pubkey, 10)}</span>
        <span className="mx-2">·</span>
        validators <span className="text-slate-300">{block.validator_count}</span>
      </div>
      {block.outcomes.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-slate-300">
          {block.outcomes.slice(0, 4).map((o) => (
            <li key={o.match_id} className="flex justify-between">
              <span className="text-slate-500">match {o.match_id}</span>
              <span>
                winner {o.winner_agent_id ?? "—"} · {o.end_reason}
              </span>
            </li>
          ))}
          {block.outcomes.length > 4 && (
            <li className="text-slate-500">+{block.outcomes.length - 4} more</li>
          )}
        </ul>
      )}
      {block.slashings && block.slashings.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs">
          {block.slashings.map((s) => (
            <li
              key={s.offender_pubkey}
              className="flex justify-between rounded bg-rose-950/40 px-1.5 py-0.5"
            >
              <span className="text-rose-300">slashed</span>
              <span className="font-mono text-rose-200">{s.offender_pubkey}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ChainExplorer() {
  const latest = useChainLatest();

  if (latest === null) {
    return (
      <div className="text-xs text-slate-500">
        chain explorer connecting<span className="animate-pulse">…</span>
      </div>
    );
  }
  if (latest.height === 0) {
    return (
      <div className="text-xs text-slate-500">
        chain height 0 — waiting for first finalised block
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-slate-400">chain height</span>
        <span className="text-slate-100">{latest.height}</span>
      </div>
      {latest.blocks
        .slice()
        .reverse()
        .map((block) => (
          <BlockCard key={block.hash} block={block} />
        ))}
    </div>
  );
}
