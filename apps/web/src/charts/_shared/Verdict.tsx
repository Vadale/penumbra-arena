/**
 * Verdict pill — shared chart primitive.
 *
 * Extracted from chart components (BLS, Beaver, Dilithium, Kyber,
 * Pedersen, Schnorr, Shamir, …) that each re-declared this same
 * pattern: a labelled accept/reject indicator with optional
 * "inverted" mode for "reject is the GOOD outcome" cases.
 *
 * `inverted=true` means the EXPECTED outcome is `ok=false`. Used
 * by tamper-test rows: tampering SHOULD cause REJECT, so an
 * inverted=true row with ok=false renders in cyan (passing).
 *
 * `okWord` / `rejectWord` allow callers to swap "ACCEPT/REJECT"
 * for "MATCH/NO MATCH", "OK/FAIL", etc. without forking the
 * component.
 */

export interface VerdictProps {
  label: string;
  ok: boolean;
  caption?: string;
  inverted?: boolean;
  okWord?: string;
  rejectWord?: string;
}

export function Verdict({
  label,
  ok,
  caption,
  inverted,
  okWord = "ACCEPT",
  rejectWord = "REJECT",
}: VerdictProps) {
  const passing = inverted ? !ok : ok;
  const verdictWord = ok ? okWord : rejectWord;
  return (
    <div
      className={
        passing
          ? "border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] p-2"
          : "border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] p-2"
      }
    >
      <div
        className={
          passing
            ? "text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]"
            : "text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)]"
        }
      >
        {label}: {verdictWord}
      </div>
      {caption ? (
        <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">{caption}</div>
      ) : null}
    </div>
  );
}
