/**
 * Coach Console — in-dashboard runner for the pna/psh CLIs.
 *
 * Backend allow-list restricts the input to pna/psh only; this
 * component exposes a small set of curated buttons plus a free-form
 * input. Output history is kept in component state (last 10 entries).
 */

import { useEffect, useState } from "react";

interface Preset {
  label: string;
  command: string;
}

interface PresetsPayload {
  attacker: Preset[];
  shell: Preset[];
}

interface ExecResult {
  id: string;
  command: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  timed_out: boolean;
  duration_ms: number;
}

const HISTORY_DEPTH = 10;

async function execCommand(command: string): Promise<{
  exit_code: number;
  stdout: string;
  stderr: string;
  timed_out: boolean;
}> {
  const response = await fetch("/coach/exec", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command }),
  });
  if (!response.ok) {
    const detail = await response.text();
    return {
      exit_code: response.status,
      stdout: "",
      stderr: detail,
      timed_out: false,
    };
  }
  return (await response.json()) as {
    exit_code: number;
    stdout: string;
    stderr: string;
    timed_out: boolean;
  };
}

export function CoachConsole() {
  const [presets, setPresets] = useState<PresetsPayload | null>(null);
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<ExecResult[]>([]);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/coach/presets");
        if (!res.ok) return;
        const payload = (await res.json()) as PresetsPayload;
        if (!cancelled) setPresets(payload);
      } catch {
        // ignore
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const runCommand = async (command: string) => {
    if (running || command.trim() === "") return;
    setRunning(true);
    const startedAt = performance.now();
    const result = await execCommand(command);
    const elapsed = performance.now() - startedAt;
    setHistory((prior) => {
      const next = [
        {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          command,
          exit_code: result.exit_code,
          stdout: result.stdout,
          stderr: result.stderr,
          timed_out: result.timed_out,
          duration_ms: elapsed,
        },
        ...prior,
      ];
      return next.slice(0, HISTORY_DEPTH);
    });
    setRunning(false);
    setInput("");
  };

  return (
    <div className="space-y-2">
      {presets && (
        <div className="space-y-1">
          <div className="text-xs uppercase tracking-wider text-slate-500">attacker</div>
          <div className="flex flex-wrap gap-1">
            {presets.attacker.map((p) => (
              <button
                key={p.command}
                type="button"
                onClick={() => void runCommand(p.command)}
                disabled={running}
                className="rounded bg-rose-900/40 px-2 py-0.5 text-xs text-rose-100 hover:bg-rose-900/70 disabled:opacity-40"
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="text-xs uppercase tracking-wider text-slate-500">shell coach</div>
          <div className="flex flex-wrap gap-1">
            {presets.shell.map((p) => (
              <button
                key={p.command}
                type="button"
                onClick={() => void runCommand(p.command)}
                disabled={running}
                className="rounded bg-sky-900/40 px-2 py-0.5 text-xs text-sky-100 hover:bg-sky-900/70 disabled:opacity-40"
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void runCommand(input);
        }}
        className="flex gap-1"
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          disabled={running}
          placeholder="pna … or psh …"
          className="flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-100 placeholder:text-slate-600 focus:border-sky-600 focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={running}
          className="rounded bg-slate-700 px-3 py-1 text-xs text-slate-100 hover:bg-slate-600 disabled:opacity-40"
        >
          run
        </button>
      </form>

      <div className="space-y-1 text-xs">
        {history.length === 0 ? (
          <div className="text-slate-500">
            No commands yet — click a preset or type `psh lessons`.
          </div>
        ) : (
          history.map((entry) => (
            <div key={entry.id} className="rounded border border-slate-800 bg-slate-900/30 p-2">
              <div className="flex items-baseline justify-between font-mono">
                <span className="text-slate-300">$ {entry.command}</span>
                <span className={entry.exit_code === 0 ? "text-emerald-400" : "text-rose-400"}>
                  exit {entry.exit_code}
                  {entry.timed_out && " (timeout)"} · {entry.duration_ms.toFixed(0)}ms
                </span>
              </div>
              {entry.stdout && (
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap font-mono text-xs text-slate-200">
                  {entry.stdout.slice(0, 1500)}
                </pre>
              )}
              {entry.stderr && (
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap font-mono text-xs text-rose-300">
                  {entry.stderr.slice(0, 800)}
                </pre>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
