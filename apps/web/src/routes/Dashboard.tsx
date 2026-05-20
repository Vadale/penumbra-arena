import { usePenumbraStore } from "../streams/store";
import { usePenumbraSocket } from "../streams/ws";
import { Arena } from "../three/Arena";

export function Dashboard() {
  usePenumbraSocket();

  const connected = usePenumbraStore((s) => s.connected);
  const lastFrame = usePenumbraStore((s) => s.lastFrame);

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-slate-800 bg-slate-900/60 px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="text-base font-medium tracking-tight">Penumbra</div>
          <div className="text-xs uppercase tracking-wider text-slate-400">Phase 1 · skeleton</div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span
            className={
              connected
                ? "rounded-full bg-emerald-900/50 px-2 py-0.5 text-emerald-300"
                : "rounded-full bg-rose-900/50 px-2 py-0.5 text-rose-300"
            }
          >
            {connected ? "connected" : "disconnected"}
          </span>
          {lastFrame && (
            <>
              <span className="text-slate-400">
                tick <span className="text-slate-100">{lastFrame.tick}</span>
              </span>
              <span className="text-slate-400">
                match <span className="text-slate-100">{lastFrame.match_id}</span>
              </span>
              <span className="text-slate-400">
                status <span className="text-slate-100">{lastFrame.match_status}</span>
              </span>
              <span className="text-slate-400">
                edges <span className="text-slate-100">{lastFrame.arena_edge_count}</span>
              </span>
            </>
          )}
        </div>
      </header>
      <main className="grid flex-1 grid-cols-[1fr_280px]">
        <section className="relative bg-slate-950">
          <Arena />
        </section>
        <aside className="border-l border-slate-800 bg-slate-900/40 p-4 text-sm">
          <div className="mb-2 text-xs uppercase tracking-wider text-slate-400">Agents</div>
          {lastFrame ? (
            <ul className="grid grid-cols-2 gap-1 text-xs text-slate-300">
              {Object.entries(lastFrame.agent_positions).map(([id, position]) => (
                <li key={id} className="flex justify-between rounded bg-slate-800/40 px-2 py-1">
                  <span className="text-slate-400">#{id}</span>
                  <span className="font-mono">node {position}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-xs text-slate-500">No frame received yet.</div>
          )}
        </aside>
      </main>
    </div>
  );
}
