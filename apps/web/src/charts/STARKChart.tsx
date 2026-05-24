/**
 * Educational FRI-STARK verifier demo panel.
 *
 * Proves a degree-7 polynomial codeword with Merkle-pinned FRI low-
 * degree testing + Fiat-Shamir challenges. Three results: honest
 * accepts, tampered evaluation rejects, tampered Merkle commitment
 * rejects. The verifier is the load-bearing artifact — production
 * STARKs (Cairo, Plonky3, RISC Zero) ship the same verifier shape
 * with many more queries for soundness < 2^-100.
 */

import { useEffect, useState } from "react";

interface Payload {
  available: boolean;
  algorithm?: string;
  domain_size?: number;
  degree_bound?: number;
  n_fri_rounds?: number;
  query_index?: number;
  final_constant?: number;
  first_commitment_short?: string;
  honest_verifies?: boolean;
  tampered_evaluation_verifies?: boolean;
  tampered_commitment_verifies?: boolean;
  soundness_note?: string;
}

export function STARKChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch("/crypto/stark/demo");
      if (res.ok) setData((await res.json()) as Payload);
    } catch {}
    setBusy(false);
  };

  useEffect(() => {
    void run();
  }, []);

  const allGood =
    data?.honest_verifies === true &&
    data?.tampered_evaluation_verifies === false &&
    data?.tampered_commitment_verifies === false;

  return (
    <div className="font-mono space-y-3">
      <div className="flex items-center gap-2 text-[10px]">
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "proving…" : "prove + verify + tamper"}
        </button>
      </div>

      {data?.available ? (
        <>
          <div className="grid grid-cols-4 gap-2 text-[10px]">
            <Stat label="algorithm" value={data.algorithm ?? "—"} accent />
            <Stat label="domain |D|" value={String(data.domain_size ?? 0)} />
            <Stat label="deg(f)" value={String(data.degree_bound ?? 0)} />
            <Stat label="FRI rounds" value={String(data.n_fri_rounds ?? 0)} />
          </div>
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <Stat label="query index" value={String(data.query_index ?? 0)} />
            <Stat label="final constant" value={String(data.final_constant ?? 0)} accent />
          </div>

          <Block label="round-0 Merkle root" value={data.first_commitment_short ?? ""} accent />

          <div className="grid grid-cols-3 gap-2 text-[10px]">
            <Stat
              label="honest"
              value={data.honest_verifies ? "ACCEPT" : "REJECT"}
              accent={data.honest_verifies}
              ember={!data.honest_verifies}
            />
            <Stat
              label="tampered evaluation"
              value={data.tampered_evaluation_verifies ? "ACCEPT" : "REJECT"}
              accent={!data.tampered_evaluation_verifies}
              ember={data.tampered_evaluation_verifies}
              caption="should reject"
            />
            <Stat
              label="tampered commitment"
              value={data.tampered_commitment_verifies ? "ACCEPT" : "REJECT"}
              accent={!data.tampered_commitment_verifies}
              ember={data.tampered_commitment_verifies}
              caption="should reject"
            />
          </div>

          <div
            className={`border px-2 py-1 text-[10px] ${
              allGood
                ? "border-[color:var(--color-penumbra-cyan)] text-[color:var(--color-penumbra-cyan)]"
                : "border-[color:var(--color-penumbra-ember)] text-[color:var(--color-penumbra-ember)]"
            }`}
          >
            {allGood ? "honest verifies + both tampers REJECTED" : "verifier soundness FAILURE"}
          </div>

          {data.soundness_note && (
            <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
              {data.soundness_note}
            </div>
          )}

          <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
            Per FRI round: prover commits a Reed-Solomon codeword via Merkle root, derives Fiat-
            Shamir β = H(transcript), folds f(x)=g(x²)+x·h(x²) into f′(x²)=g(x²)+β·h(x²). After
            log|D| rounds the polynomial collapses to a constant. Verifier checks each fold's (f(x),
            f(−x)) → f′(x²) relation under the round's β. Merkle paths + transcript binding prevent
            rewinding.
          </div>
        </>
      ) : (
        <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
          {busy ? "running STARK demo…" : "click prove + verify + tamper"}
        </div>
      )}
    </div>
  );
}

function Block({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div
        className={`border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-2 text-[11px] break-all ${
          accent
            ? "text-[color:var(--color-penumbra-cyan)]"
            : "text-[color:var(--color-penumbra-text)]"
        }`}
      >
        0x{value}…
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
  ember,
  caption,
}: {
  label: string;
  value: string;
  accent?: boolean;
  ember?: boolean;
  caption?: string;
}) {
  const cls = ember
    ? "text-[color:var(--color-penumbra-ember)]"
    : accent
      ? "text-[color:var(--color-penumbra-cyan)]"
      : "text-[color:var(--color-penumbra-text)]";
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div className={`tabular-nums ${cls}`}>{value}</div>
      {caption && (
        <div className="text-[8px] text-[color:var(--color-penumbra-dim)]">{caption}</div>
      )}
    </div>
  );
}
