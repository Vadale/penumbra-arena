/**
 * Yao's millionaires — two parties learn ONLY who has more, never the values.
 *
 * Garbled circuit primitive evaluated bit-by-bit on a 16-bit
 * comparator. AND/OR/XOR gates each ship 4 encrypted rows; the
 * evaluator decrypts exactly one row per gate using its OT-selected
 * input label.
 */

import { useEffect, useState } from "react";
import { FetchError, Stat, Verdict } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  a?: number;
  b?: number;
  relation?: "a_less" | "b_less" | "equal";
  expected_relation?: string;
  honest_comparator_correct?: boolean;
  tampered_label_decodes_to_valid_output?: boolean;
  control_correct_decryption_works?: boolean;
}

export function YaoChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/crypto/yao/demo");
      if (!res.ok) {
        setError(`HTTP ${res.status} on /crypto/yao/demo`);
      } else {
        setData((await res.json()) as Payload);
      }
    } catch (exc) {
      setError(`network error: ${exc instanceof Error ? exc.message : String(exc)}`);
    }
    setBusy(false);
  };

  useEffect(() => {
    void run();
  }, []);

  if (!data?.available) {
    if (error) return <FetchError message={error} />;
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {busy ? "garbling circuit…" : "Yao unavailable"}
      </div>
    );
  }

  const relationLabel =
    data.relation === "a_less"
      ? "a < b"
      : data.relation === "b_less"
        ? "a > b"
        : data.relation === "equal"
          ? "a = b"
          : "—";

  return (
    <div className="font-mono space-y-3">
      {error && <FetchError message={error} />}
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value="garbled circuits" accent />
        <Stat label="gates / bit" value="3 (XOR + 2 AND)" />
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "running…" : "re-run"}
        </button>
      </div>

      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="alice's a" value={String(data.a ?? 0)} accent />
        <Stat label="bob's b" value={String(data.b ?? 0)} accent />
        <Stat label="relation revealed" value={relationLabel} accent />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Verdict
          label="comparator correct"
          ok={data.honest_comparator_correct ?? false}
          caption="garbled-circuit output matches truth"
        />
        <Verdict
          label="tampered label rejected"
          ok={data.tampered_label_decodes_to_valid_output ?? true}
          inverted
          caption="wrong wire label → MAC fails"
        />
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Each wire carries 2 random 128-bit labels (one per bit value); each gate ships 4 doubly-
        encrypted output labels; the evaluator decrypts EXACTLY ONE row per gate using the input
        labels it received via OT. The output label decodes to {"{0, 1}"} — and only that bit leaks.
      </div>
    </div>
  );
}
