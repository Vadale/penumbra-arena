/**
 * Private Set Intersection — Alice + Bob find their common items, nothing else.
 *
 * OPRF-based PSI: each party homomorphically blinds its items
 * before they go on the wire. Only the intersection comes out as
 * plaintext on Alice's side; Bob learns nothing.
 */

import { useEffect, useState } from "react";
import { Stat, Verdict } from "./_shared";

interface Payload {
  available: boolean;
  algorithm?: string;
  alice_set_size?: number;
  bob_set_size?: number;
  intersection?: string[];
  intersection_size?: number;
  expected_intersection_size?: number;
  honest_correct?: boolean;
  tampered_published_intersection_size?: number;
  tamper_changes_intersection?: boolean;
}

export function PSIChart() {
  const [data, setData] = useState<Payload | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const res = await fetch("/crypto/psi/demo");
      if (res.ok) setData((await res.json()) as Payload);
    } catch {}
    setBusy(false);
  };

  useEffect(() => {
    void run();
  }, []);

  if (!data?.available) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {busy ? "running OPRF…" : "PSI unavailable"}
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="algorithm" value="OPRF / DH" accent />
        <Stat label="alice |S_A|" value={String(data.alice_set_size ?? 0)} />
        <Stat label="bob |S_B|" value={String(data.bob_set_size ?? 0)} />
      </div>

      <div className="flex items-center gap-2 text-[10px]">
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "intersecting…" : "re-run"}
        </button>
        <span className="text-[color:var(--color-penumbra-dim)]">
          intersection learned by Alice (Bob learns nothing):
        </span>
      </div>

      <div className="flex flex-wrap gap-1 text-[11px]">
        {(data.intersection ?? []).map((item) => (
          <span
            key={item}
            className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[color:var(--color-penumbra-cyan)]"
          >
            {item}
          </span>
        ))}
        {(data.intersection ?? []).length === 0 && (
          <span className="text-[color:var(--color-penumbra-dim)]">∅ — empty intersection</span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Verdict
          label="honest intersection"
          ok={data.honest_correct ?? false}
          caption={`size ${data.intersection_size ?? 0} = expected ${data.expected_intersection_size ?? 0}`}
        />
        <Verdict
          label="tamper detected"
          ok={data.tamper_changes_intersection ?? false}
          caption={`bob's tampered set → ${data.tampered_published_intersection_size ?? 0} matches`}
        />
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Both parties evaluate the OPRF on their items: Alice ships {"{H(x)^α}"}, Bob raises by his
        secret β and publishes {"{H(y)^β}"}. Alice removes α and compares. Bob never sees Alice's
        items; Alice sees only the intersection.
      </div>
    </div>
  );
}
