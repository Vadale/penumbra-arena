/**
 * Sandboxed Python REPL console.
 *
 * Opens a JSON-over-WS channel to /ws/repl. Each submission goes
 * through the server-side Penumbra `api` namespace; no host
 * filesystem or subprocess access from the browser.
 */

import { useEffect, useRef, useState } from "react";

interface Entry {
  kind: "in" | "out" | "err";
  text: string;
}

const REPL_WS_URL = (() => {
  if (typeof window === "undefined") return "";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/repl`;
})();

export function ReplConsole() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [input, setInput] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/repl/status")
      .then((r) => r.json())
      .then((d: { enabled: boolean }) => {
        if (!cancelled) setEnabled(d.enabled);
      })
      .catch(() => {
        if (!cancelled) setEnabled(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (enabled !== true) return;
    const ws = new WebSocket(REPL_WS_URL);
    wsRef.current = ws;
    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data as string) as {
          type: string;
          stdout?: string;
          stderr?: string;
        };
        if (parsed.type === "result") {
          if (parsed.stdout) {
            setEntries((e) => [...e, { kind: "out", text: parsed.stdout ?? "" }]);
          }
          if (parsed.stderr) {
            setEntries((e) => [...e, { kind: "err", text: parsed.stderr ?? "" }]);
          }
        }
      } catch {
        // ignore malformed messages
      }
    };
    ws.onclose = () => {
      setEntries((e) => [...e, { kind: "err", text: "[connection closed]\n" }]);
    };
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [enabled]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll on every entry append.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [entries.length]);

  const submit = () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const text = input.trim();
    if (!text) return;
    setEntries((e) => [...e, { kind: "in", text: `>>> ${text}\n` }]);
    ws.send(JSON.stringify({ type: "submit", source: text }));
    setInput("");
  };

  if (enabled === null) {
    return <div className="text-xs text-slate-500">checking REPL availability…</div>;
  }
  if (enabled === false) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-400">
        <div className="mb-1 text-slate-300">Python REPL disabled</div>
        <p>
          Set <code className="font-mono text-slate-200">PENUMBRA_ENABLE_REPL=1</code> in the
          backend environment to enable the sandboxed attacker REPL. The PTY tab gives you
          unrestricted host shell access; this would give you a read-only Python view of the
          orchestrator state.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto rounded border border-slate-800 bg-slate-900/40 p-2 font-mono text-xs">
        {entries.map((entry, i) => (
          <pre
            // biome-ignore lint/suspicious/noArrayIndexKey: append-only log; rows never reorder.
            key={`${entry.kind}-${i}`}
            className={
              entry.kind === "in"
                ? "whitespace-pre-wrap text-slate-300"
                : entry.kind === "err"
                  ? "whitespace-pre-wrap text-rose-300"
                  : "whitespace-pre-wrap text-slate-100"
            }
          >
            {entry.text}
          </pre>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="mt-2 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          placeholder="api.snapshot()"
          className="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-100 placeholder:text-slate-600 focus:border-slate-500 focus:outline-none"
        />
        <button
          type="button"
          onClick={submit}
          className="rounded bg-slate-200 px-3 py-1 text-xs font-medium text-slate-900 hover:bg-white"
        >
          run
        </button>
      </div>
    </div>
  );
}
