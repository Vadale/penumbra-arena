/**
 * Phase 5 Tier 4 — Capture-the-flag tile.
 *
 * Lists the YAML-defined challenges, lets the user submit a flag for
 * the selected one, and shows the per-challenge leaderboard.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Challenge {
  id: string;
  title: string;
  setup: Record<string, unknown>;
  acceptance: Record<string, unknown>;
  solvers: number;
}

interface SubmitResult {
  correct: boolean;
  expected_flag_prefix?: string;
}

interface LeaderboardRow {
  rank: number;
  session_id: string;
  submitted_at: number;
}

export function CTFChart() {
  const [challenges, setChallenges] = useState<Challenge[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState("anonymous");
  const [flag, setFlag] = useState("");
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [board, setBoard] = useState<LeaderboardRow[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch("/ctf/challenges");
        if (!r.ok) return;
        const body = (await r.json()) as { challenges?: Challenge[] };
        const list = body.challenges ?? [];
        setChallenges(list);
        if (list[0] && !selected) setSelected(list[0].id);
      } catch {}
    };
    void load();
  }, []);

  useEffect(() => {
    if (!selected) {
      setBoard([]);
      return;
    }
    const load = async () => {
      try {
        const r = await fetch(`/ctf/leaderboard/${encodeURIComponent(selected)}`);
        if (!r.ok) return;
        const body = (await r.json()) as { leaderboard?: LeaderboardRow[] };
        setBoard(body.leaderboard ?? []);
      } catch {}
    };
    void load();
  }, [selected]);

  const submit = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const r = await fetch(`/ctf/submit/${encodeURIComponent(selected)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flag, session_id: sessionId }),
      });
      if (r.ok) {
        setResult((await r.json()) as SubmitResult);
        const board2 = await fetch(`/ctf/leaderboard/${encodeURIComponent(selected)}`);
        if (board2.ok) {
          const body = (await board2.json()) as { leaderboard?: LeaderboardRow[] };
          setBoard(body.leaderboard ?? []);
        }
      }
    } catch {}
    setBusy(false);
  };

  const current = challenges.find((c) => c.id === selected) ?? null;

  return (
    <div className="font-mono space-y-3">
      <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
        Solve a privacy / crypto attack challenge, submit the resulting flag, climb the
        per-challenge leaderboard. Hints live in the YAML next to each challenge id.
      </div>
      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <div>
          <label className="block uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
            challenge
          </label>
          <select
            value={selected ?? ""}
            onChange={(e) => setSelected(e.target.value)}
            className="w-full border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
          >
            {challenges.map((c) => (
              <option key={c.id} value={c.id}>
                {c.id}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
            session id
          </label>
          <input
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            className="w-full border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
          />
        </div>
      </div>

      {current && (
        <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-2 text-[10px]">
          <div className="mb-1 text-[color:var(--color-penumbra-cyan)]">{current.title}</div>
          <pre className="whitespace-pre-wrap break-words text-[10px] text-[color:var(--color-penumbra-muted)]">
            setup: {JSON.stringify(current.setup, null, 2)}
          </pre>
          <pre className="whitespace-pre-wrap break-words text-[10px] text-[color:var(--color-penumbra-muted)]">
            acceptance: {JSON.stringify(current.acceptance, null, 2)}
          </pre>
        </div>
      )}

      <div className="flex items-center gap-2 text-[10px]">
        <input
          value={flag}
          onChange={(e) => setFlag(e.target.value)}
          placeholder="PEN{...}"
          className="flex-1 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <button
          type="button"
          onClick={submit}
          disabled={busy || !selected}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          submit
        </button>
      </div>

      {result && (
        <div className="grid grid-cols-2 gap-2 text-[10px]">
          <Stat
            label="result"
            value={result.correct ? "correct" : "wrong"}
            accent={result.correct}
            ember={!result.correct}
          />
          <Stat label="expected" value={result.expected_flag_prefix ?? "—"} />
        </div>
      )}

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          leaderboard — {selected ?? "—"} ({board.length})
        </div>
        {board.length === 0 ? (
          <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">no solvers yet</div>
        ) : (
          <table className="w-full text-[10px]">
            <thead className="text-[color:var(--color-penumbra-dim)]">
              <tr>
                <th className="text-left font-normal">rank</th>
                <th className="text-left font-normal">session</th>
                <th className="text-right font-normal">at</th>
              </tr>
            </thead>
            <tbody>
              {board.map((row) => (
                <tr
                  key={row.session_id}
                  className="border-t border-[color:var(--color-penumbra-border)]"
                >
                  <td className="py-1 tabular-nums text-[color:var(--color-penumbra-text)]">
                    {row.rank}
                  </td>
                  <td className="py-1 text-[color:var(--color-penumbra-text)]">{row.session_id}</td>
                  <td className="py-1 text-right tabular-nums text-[color:var(--color-penumbra-muted)]">
                    {new Date(row.submitted_at * 1000).toLocaleTimeString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
