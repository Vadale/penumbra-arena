/**
 * World snapshot save/load UI.
 *
 * Lists existing snapshots, lets the user save the current state
 * under a name, and load any saved snapshot. All endpoints already
 * exist on the backend.
 */

import { useEffect, useState } from "react";

interface Snapshot {
  name: string;
  size_bytes: number;
  saved_at: number; // epoch ns
}

export function WorldSnapshotChart() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [name, setName] = useState("checkpoint-A");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const res = await fetch("/world/list");
      if (!res.ok) return;
      const payload = (await res.json()) as { snapshots?: Snapshot[] };
      setSnapshots(payload.snapshots ?? []);
    } catch {}
  };

  useEffect(() => {
    void refresh();
    const t = window.setInterval(refresh, 4000);
    return () => window.clearInterval(t);
  }, [refresh]);

  const save = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/world/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      setMessage(res.ok ? `saved ${name}` : `error ${res.status}`);
    } catch {
      setMessage("network error");
    }
    setBusy(false);
    await refresh();
  };

  const load = async (n: string) => {
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/world/load", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: n }),
      });
      setMessage(res.ok ? `loaded ${n}` : `error ${res.status}`);
    } catch {
      setMessage("network error");
    }
    setBusy(false);
  };

  return (
    <div className="font-mono space-y-3">
      <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
        Snapshots capture the full perpetual simulation state: chain head, agent positions +
        policies, encrypted heatmap state, market wallets + treasuries, and the RNG cursor. Load any
        one to roll back.
      </div>

      <div className="flex items-center gap-2 text-[10px]">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="snapshot name"
          className="w-40 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <button
          type="button"
          onClick={save}
          disabled={busy || !name.trim()}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "saving…" : "save current state"}
        </button>
        {message && (
          <span className="text-[10px] text-[color:var(--color-penumbra-muted)]">{message}</span>
        )}
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          saved snapshots ({snapshots.length})
        </div>
        {snapshots.length === 0 ? (
          <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
            no snapshots yet — type a name and click save
          </div>
        ) : (
          <table className="w-full text-[10px]">
            <thead className="text-[color:var(--color-penumbra-dim)]">
              <tr>
                <th className="text-left font-normal">name</th>
                <th className="text-left font-normal">size</th>
                <th className="text-right font-normal" />
              </tr>
            </thead>
            <tbody>
              {snapshots.map((s) => (
                <tr key={s.name} className="border-t border-[color:var(--color-penumbra-border)]">
                  <td className="py-1 text-[color:var(--color-penumbra-text)]">{s.name}</td>
                  <td className="py-1 tabular-nums text-[color:var(--color-penumbra-muted)]">
                    {(s.size_bytes / 1024).toFixed(1)} KB
                  </td>
                  <td className="py-1 text-right">
                    <button
                      type="button"
                      onClick={() => void load(s.name)}
                      disabled={busy}
                      className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-0.5 text-[9px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
                    >
                      load
                    </button>
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
