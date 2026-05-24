/**
 * FetchError — shared chart error display.
 *
 * Renders inside a tile when a backend fetch fails. Pairs with the
 * `useFetchJsonOnce` / `useFetchJsonPoll` hooks (see
 * `hooks/useFetchJson.ts`) which surface a `{ kind: "error",
 * message }` state instead of silently swallowing failures.
 *
 * Visual:
 *   - Ember (orange) border + tinted background — same convention as
 *     the `ember` flag on `Stat`.
 *   - Leading "[!]" text marker so colorblind users still get the
 *     failure signal without relying on hue.
 *   - Monospace, fits inside the existing Stat-cell footprint without
 *     breaking tile layout.
 */

export interface FetchErrorProps {
  message: string;
}

export function FetchError({ message }: FetchErrorProps) {
  return (
    <div
      role="alert"
      className="border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-2 py-1 font-mono text-[10px] text-[color:var(--color-penumbra-ember)] break-all"
    >
      <span className="mr-1 uppercase tracking-wider">[!] fetch</span>
      <span className="text-[color:var(--color-penumbra-text)]">{message}</span>
    </div>
  );
}
