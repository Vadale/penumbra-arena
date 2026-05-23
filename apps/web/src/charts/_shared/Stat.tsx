/**
 * Stat cell — shared chart primitive.
 *
 * Extracted from ~45 chart components that each re-declared an
 * identical local helper. One canonical visual style for all
 * label / value tiles.
 *
 * Conventions:
 * - `accent` (cyan) — successful / good / "data is here" state.
 * - `ember` (orange) — warning / failed / "watch this" state.
 * - Neither → default (white-ish foreground).
 * - `caption` — optional small line beneath the value.
 */

export interface StatProps {
  label: string;
  value: string | number;
  accent?: boolean;
  ember?: boolean;
  caption?: string;
}

export function Stat({ label, value, accent, ember, caption }: StatProps) {
  const valueClass = ember
    ? "text-[color:var(--color-penumbra-ember)]"
    : accent
      ? "text-[color:var(--color-penumbra-cyan)]"
      : "text-[color:var(--color-penumbra-text)]";
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div className={`tabular-nums ${valueClass}`}>{value}</div>
      {caption ? (
        <div className="text-[8px] text-[color:var(--color-penumbra-dim)]">{caption}</div>
      ) : null}
    </div>
  );
}
