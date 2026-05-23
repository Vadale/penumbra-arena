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
 * - `digits` — when value is a finite number, format with this many
 *   decimal places. Use `digits="adaptive"` (default) to mimic the
 *   common "3 decimals for small magnitudes, 0 for large" pattern.
 * - `suffix` — appended after the (formatted) value, e.g. "%", "ms".
 */

export interface StatProps {
  label: string;
  value: string | number;
  accent?: boolean;
  ember?: boolean;
  caption?: string;
  digits?: number | "adaptive";
  suffix?: string;
}

function formatValue(value: string | number, digits?: number | "adaptive"): string {
  if (typeof value !== "number") return String(value);
  if (!Number.isFinite(value)) return String(value);
  if (digits === undefined) return String(value);
  if (digits === "adaptive") {
    const abs = Math.abs(value);
    if (abs >= 1000) return value.toFixed(0);
    if (abs >= 10) return value.toFixed(2);
    return value.toFixed(3);
  }
  return value.toFixed(digits);
}

export function Stat({ label, value, accent, ember, caption, digits, suffix }: StatProps) {
  const valueClass = ember
    ? "text-[color:var(--color-penumbra-ember)]"
    : accent
      ? "text-[color:var(--color-penumbra-cyan)]"
      : "text-[color:var(--color-penumbra-text)]";
  const rendered = formatValue(value, digits) + (suffix ?? "");
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div className={`tabular-nums ${valueClass}`}>{rendered}</div>
      {caption ? (
        <div className="text-[8px] text-[color:var(--color-penumbra-dim)]">{caption}</div>
      ) : null}
    </div>
  );
}
