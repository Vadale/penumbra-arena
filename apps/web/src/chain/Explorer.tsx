/**
 * Chain Explorer side panel — DF-density.
 *
 * Polls /chain/latest at 3 Hz; each block becomes a tight monospace
 * row listing height · hash · proposer · validators · outcome count.
 * Slashings render as an ember-tinted row.
 */

import type { BlockView } from "../streams/chain";
import { useChainLatest } from "../streams/chain";

function hashPrefix(hex: string, n = 10): string {
  return hex.length > n ? `${hex.slice(0, n)}…` : hex;
}

function BlockRow({ block }: { block: BlockView }) {
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1.5">
      <div className="flex items-baseline justify-between">
        <span className="text-[color:var(--color-penumbra-cyan)] tabular-nums">
          #{block.height}
        </span>
        <span className="font-mono text-[10px] text-[color:var(--color-penumbra-muted)]">
          {hashPrefix(block.hash)}
        </span>
      </div>
      <div className="mt-0.5 text-[10px] text-[color:var(--color-penumbra-dim)]">
        prop{" "}
        <span className="font-mono text-[color:var(--color-penumbra-muted)]">
          {hashPrefix(block.proposer_pubkey, 8)}
        </span>
        <span className="mx-1.5">·</span>
        <span className="text-[color:var(--color-penumbra-text)]">{block.validator_count}</span> val
        {block.outcomes.length > 0 && (
          <>
            <span className="mx-1.5">·</span>
            <span className="text-[color:var(--color-penumbra-text)]">{block.outcomes.length}</span>{" "}
            tx
          </>
        )}
      </div>
      {block.outcomes.length > 0 && (
        <ul className="mt-1 space-y-0 text-[10px]">
          {block.outcomes.slice(0, 3).map((o) => (
            <li
              key={o.match_id}
              className="flex justify-between text-[color:var(--color-penumbra-text)]"
            >
              <span className="text-[color:var(--color-penumbra-dim)]">m{o.match_id}</span>
              <span>
                w{o.winner_agent_id ?? "—"}{" "}
                <span className="text-[color:var(--color-penumbra-dim)]">{o.end_reason}</span>
              </span>
            </li>
          ))}
          {block.outcomes.length > 3 && (
            <li className="text-[color:var(--color-penumbra-dim)]">+{block.outcomes.length - 3}</li>
          )}
        </ul>
      )}
      {block.slashings && block.slashings.length > 0 && (
        <ul className="mt-1 space-y-0 text-[10px]">
          {block.slashings.map((s) => (
            <li
              key={s.offender_pubkey}
              className="flex justify-between border border-[color:var(--color-penumbra-ember-bg)] bg-[color:var(--color-penumbra-ember-bg)] px-1 text-[color:var(--color-penumbra-ember)]"
            >
              <span>⚠ slashed</span>
              <span className="font-mono">{s.offender_pubkey}</span>
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
      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
        chain explorer connecting<span className="animate-pulse">…</span>
      </div>
    );
  }
  if (latest.height === 0) {
    return (
      <div className="text-[10px] text-[color:var(--color-penumbra-muted)]">
        chain height 0 — waiting for first finalised block
      </div>
    );
  }
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between text-[10px]">
        <span className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          height
        </span>
        <span className="tabular-nums text-[color:var(--color-penumbra-cyan)] text-sm">
          #{latest.height}
        </span>
      </div>
      {latest.blocks
        .slice()
        .reverse()
        .map((block) => (
          <BlockRow key={block.hash} block={block} />
        ))}
    </div>
  );
}
