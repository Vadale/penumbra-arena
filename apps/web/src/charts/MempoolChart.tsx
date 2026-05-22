/**
 * Mempool view — pending match outcomes + pending slashings.
 *
 * Live snapshot of what will be folded into the NEXT block.
 */

import { useEffect, useState } from "react";

interface Outcome {
  match_id: number;
  winner: number | null;
  winning_goal: number | null;
  started_tick: number;
  end_tick: number;
  end_reason: string;
}
interface Slashing {
  offender_short: string;
  height: number;
}
interface Mempool {
  n_outcomes: number;
  outcomes: Outcome[];
  n_slashings: number;
  slashings: Slashing[];
}

export function MempoolChart() {
  const [data, setData] = useState<Mempool | null>(null);
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await fetch("/chain/mempool");
        if (!res.ok) return;
        const payload = (await res.json()) as Mempool;
        if (!cancelled) setData(payload);
      } catch {}
    };
    void tick();
    const t = window.setInterval(tick, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  if (!data) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        loading mempool…
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <Stat label="pending outcomes" value={data.n_outcomes} accent={data.n_outcomes > 0} />
        <Stat label="pending slashings" value={data.n_slashings} ember={data.n_slashings > 0} />
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          outcomes queued for next block ({data.outcomes.length}/{data.n_outcomes})
        </div>
        {data.outcomes.length === 0 ? (
          <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">empty</div>
        ) : (
          <table className="w-full text-[10px]">
            <thead className="text-[color:var(--color-penumbra-dim)]">
              <tr>
                <th className="text-left font-normal">match</th>
                <th className="text-left font-normal">winner</th>
                <th className="text-left font-normal">goal</th>
                <th className="text-left font-normal">ticks</th>
                <th className="text-left font-normal">reason</th>
              </tr>
            </thead>
            <tbody>
              {data.outcomes.map((o) => (
                <tr
                  key={`m-${o.match_id}`}
                  className="border-t border-[color:var(--color-penumbra-border)]"
                >
                  <td className="py-0.5 text-[color:var(--color-penumbra-cyan)]">#{o.match_id}</td>
                  <td className="py-0.5 text-[color:var(--color-penumbra-text)]">
                    {o.winner !== null ? `agent ${o.winner}` : "—"}
                  </td>
                  <td className="py-0.5 text-[color:var(--color-penumbra-text)]">
                    {o.winning_goal !== null ? `#${o.winning_goal}` : "—"}
                  </td>
                  <td className="py-0.5 tabular-nums text-[color:var(--color-penumbra-muted)]">
                    {o.started_tick}-{o.end_tick}
                  </td>
                  <td
                    className={
                      o.end_reason === "won"
                        ? "py-0.5 text-[color:var(--color-penumbra-cyan)]"
                        : "py-0.5 text-[color:var(--color-penumbra-ember)]"
                    }
                  >
                    {o.end_reason}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {data.slashings.length > 0 && (
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)]">
            slashing evidence queued
          </div>
          <table className="w-full text-[10px]">
            {data.slashings.map((s) => (
              <tr
                key={`s-${s.offender_short}-${s.height}`}
                className="border-t border-[color:var(--color-penumbra-border)]"
              >
                <td className="py-0.5 text-[color:var(--color-penumbra-ember)]">
                  offender {s.offender_short}…
                </td>
                <td className="py-0.5 tabular-nums text-[color:var(--color-penumbra-muted)]">
                  height {s.height}
                </td>
              </tr>
            ))}
          </table>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
  ember,
}: {
  label: string;
  value: number;
  accent?: boolean;
  ember?: boolean;
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
    </div>
  );
}
