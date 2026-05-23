/**
 * Hex Block display — shared chart primitive.
 *
 * Extracted from 5 chart components (Dilithium, Kyber, Pedersen,
 * Schnorr, VDF) that each re-declared this same pattern: a small
 * label + a monospace box with truncated hex content followed by
 * ellipsis.
 *
 * `accent=true` highlights the block in cyan (used for emphasised
 * values like derived secrets, aggregate sums, etc.).
 */

export interface BlockProps {
  label: string;
  value: string;
  accent?: boolean;
  prefix?: string; // e.g. "0x" — defaults to nothing
}

export function Block({ label, value, accent, prefix = "" }: BlockProps) {
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div
        className={`border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-2 text-[11px] break-all ${accent ? "text-[color:var(--color-penumbra-cyan)]" : "text-[color:var(--color-penumbra-text)]"}`}
      >
        {prefix}
        {value}…
      </div>
    </div>
  );
}
