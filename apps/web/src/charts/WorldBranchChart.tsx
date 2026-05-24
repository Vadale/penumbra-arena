/**
 * Phase 5 Tier 4 — World branching tile.
 *
 * Snapshot the live simulation into N in-memory clones, advance any
 * branch independently, and compare side-by-side (current tick,
 * position vectors, wealth distribution).
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface Branch {
  branch_id: string;
  parent_tick: number;
  current_tick: number;
  n_agents: number;
}

interface CompareRow {
  branch_id: string;
  current_tick: number;
  positions: number[];
  wealth: number[];
  n_agents: number;
}

export function WorldBranchChart() {
  const [name, setName] = useState("exp");
  const [nBranches, setNBranches] = useState(3);
  const [advanceTicks, setAdvanceTicks] = useState(5);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [diff, setDiff] = useState<CompareRow[] | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      const r = await fetch("/world/branches");
      if (!r.ok) return;
      const body = (await r.json()) as { branches?: Branch[] };
      setBranches(body.branches ?? []);
    } catch {}
  };

  useEffect(() => {
    void refresh();
    const t = window.setInterval(refresh, 4000);
    return () => window.clearInterval(t);
  }, []);

  const createBranches = async () => {
    setBusy(true);
    try {
      await fetch("/world/branch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, n_branches: nBranches }),
      });
      await refresh();
    } catch {}
    setBusy(false);
  };

  const advance = async (branchId: string) => {
    setBusy(true);
    try {
      await fetch(`/world/branch/${encodeURIComponent(branchId)}/advance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticks: advanceTicks }),
      });
      await refresh();
    } catch {}
    setBusy(false);
  };

  const compare = async () => {
    if (selected.length === 0) return;
    setBusy(true);
    try {
      const r = await fetch("/world/branches/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ branch_ids: selected }),
      });
      if (r.ok) {
        const body = (await r.json()) as { branches?: CompareRow[] };
        setDiff(body.branches ?? []);
      }
    } catch {}
    setBusy(false);
  };

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  return (
    <div className="font-mono space-y-3">
      <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
        Branch: in-memory pickle-clones of the live simulation. Each branch advances on its own; the
        compare panel diffs current_tick, per-agent positions, and per-agent wealth side by side.
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[10px]">
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          base name
        </label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-28 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">n</label>
        <input
          type="number"
          min={1}
          max={20}
          value={nBranches}
          onChange={(e) => setNBranches(Number(e.target.value))}
          className="w-14 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <button
          type="button"
          onClick={createBranches}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "…" : "branch"}
        </button>
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          advance ticks
        </label>
        <input
          type="number"
          min={1}
          max={1000}
          value={advanceTicks}
          onChange={(e) => setAdvanceTicks(Number(e.target.value))}
          className="w-16 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <button
          type="button"
          onClick={compare}
          disabled={busy || selected.length === 0}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          compare ({selected.length})
        </button>
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          branches ({branches.length})
        </div>
        {branches.length === 0 ? (
          <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
            no branches yet — click branch
          </div>
        ) : (
          <table className="w-full text-[10px]">
            <thead className="text-[color:var(--color-penumbra-dim)]">
              <tr>
                <th className="text-left font-normal">sel</th>
                <th className="text-left font-normal">id</th>
                <th className="text-right font-normal">parent</th>
                <th className="text-right font-normal">current</th>
                <th className="text-right font-normal" />
              </tr>
            </thead>
            <tbody>
              {branches.map((b) => (
                <tr
                  key={b.branch_id}
                  className="border-t border-[color:var(--color-penumbra-border)]"
                >
                  <td className="py-1">
                    <input
                      type="checkbox"
                      checked={selected.includes(b.branch_id)}
                      onChange={() => toggle(b.branch_id)}
                    />
                  </td>
                  <td className="py-1 text-[color:var(--color-penumbra-text)]">{b.branch_id}</td>
                  <td className="py-1 text-right tabular-nums text-[color:var(--color-penumbra-muted)]">
                    {b.parent_tick}
                  </td>
                  <td className="py-1 text-right tabular-nums text-[color:var(--color-penumbra-text)]">
                    {b.current_tick}
                  </td>
                  <td className="py-1 text-right">
                    <button
                      type="button"
                      onClick={() => void advance(b.branch_id)}
                      disabled={busy}
                      className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-0.5 text-[9px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
                    >
                      advance
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {diff && diff.length > 0 && (
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
            side-by-side diff
          </div>
          <div
            className="grid gap-2"
            style={{ gridTemplateColumns: `repeat(${Math.min(diff.length, 3)}, minmax(0, 1fr))` }}
          >
            {diff.map((row) => {
              const meanWealth =
                row.wealth.length > 0
                  ? row.wealth.reduce((s, x) => s + x, 0) / row.wealth.length
                  : 0;
              return (
                <div
                  key={row.branch_id}
                  className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-2"
                >
                  <div className="text-[10px] text-[color:var(--color-penumbra-cyan)]">
                    {row.branch_id}
                  </div>
                  <div className="text-[9px] text-[color:var(--color-penumbra-muted)]">
                    tick {row.current_tick} · {row.n_agents} agents · mean wealth{" "}
                    {meanWealth.toFixed(2)}
                  </div>
                  <div className="mt-1 break-all text-[9px] text-[color:var(--color-penumbra-dim)]">
                    pos[{row.positions.slice(0, 12).join(", ")}
                    {row.positions.length > 12 ? ", …" : ""}]
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="branches" value={branches.length} digits={0} />
        <Stat label="selected" value={selected.length} digits={0} accent={selected.length > 0} />
        <Stat label="last cmp rows" value={diff?.length ?? 0} digits={0} />
      </div>
    </div>
  );
}
