/**
 * Phase 5 Tier 4 — Custom policy injection.
 *
 * Paste Python defining `def policy(state, observation)`; the backend
 * sandboxes it (whitelisted builtins + numpy + math), runs a one-shot
 * smoke test, and registers it under the chosen name. The textarea is
 * plain (no Monaco) on purpose to keep the dashboard bundle small.
 */

import { useEffect, useState } from "react";
import { Stat } from "./_shared";

interface PolicyRow {
  name: string;
  scope: string;
  source_chars: string;
}

interface RegisterResult {
  name?: string;
  scope?: string;
  source_chars?: number;
  try?: { ok?: boolean; result?: string; error?: string };
}

function firstLine(text: string): string {
  const stripped = text.trim();
  if (stripped.length === 0) return "policy rejected";
  for (const line of stripped.split("\n").reverse()) {
    const candidate = line.trim();
    if (candidate.length > 0 && !candidate.startsWith("File ") && !candidate.startsWith("at ")) {
      return candidate;
    }
  }
  return stripped.split("\n")[0] ?? stripped;
}

const DEFAULT_SOURCE = `def policy(state, observation):
    # whitelisted: np, math, builtin numerics.
    # state and observation are dicts at try time (empty for the smoke run).
    return 0
`;

export function CustomPolicyChart() {
  const [name, setName] = useState("custom_one");
  const [scope, setScope] = useState("all");
  const [source, setSource] = useState(DEFAULT_SOURCE);
  const [policies, setPolicies] = useState<PolicyRow[]>([]);
  const [lastResult, setLastResult] = useState<RegisterResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const r = await fetch("/attacker/policies");
      if (!r.ok) return;
      const body = (await r.json()) as { policies?: PolicyRow[] };
      setPolicies(body.policies ?? []);
    } catch {}
  };

  useEffect(() => {
    void refresh();
  }, []);

  const tryRun = async () => {
    setBusy(true);
    setErrorMsg(null);
    try {
      const r = await fetch("/attacker/policy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, code: source, scope }),
      });
      if (r.status !== 200) {
        const detail = await r.text();
        setErrorMsg(`HTTP ${r.status}: ${detail}`);
        setLastResult(null);
      } else {
        const body = (await r.json()) as RegisterResult;
        setLastResult(body);
        await refresh();
      }
    } catch (e) {
      setErrorMsg(`network: ${String(e)}`);
    }
    setBusy(false);
  };

  const remove = async (n: string) => {
    setBusy(true);
    try {
      await fetch(`/attacker/policy/${encodeURIComponent(n)}`, { method: "DELETE" });
      await refresh();
    } catch {}
    setBusy(false);
  };

  return (
    <div className="font-mono space-y-3">
      <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
        Define <code>policy(state, observation)</code>. Whitelisted: <code>np</code>,{" "}
        <code>math</code>, basic builtins. Forbidden: <code>import</code>, <code>open</code>,{" "}
        <code>eval</code>, dunders. 50ms wall-clock budget per call.
      </div>
      <div className="flex items-center gap-2 text-[10px]">
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          name
        </label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-40 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          scope
        </label>
        <input
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          className="w-32 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
      </div>
      <textarea
        value={source}
        onChange={(e) => setSource(e.target.value)}
        spellCheck={false}
        rows={10}
        className="w-full resize-y border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-2 font-mono text-[11px] text-[color:var(--color-penumbra-text)]"
      />
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={tryRun}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "registering…" : "try + register"}
        </button>
        <button
          type="button"
          onClick={() => void remove(name)}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-ember)] disabled:opacity-50"
        >
          remove
        </button>
      </div>

      {errorMsg && (
        <div className="border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-2 py-2 text-[10px] text-[color:var(--color-penumbra-ember)]">
          <div className="font-semibold uppercase tracking-wider">policy rejected</div>
          <div className="mt-1 text-[11px] text-[color:var(--color-penumbra-text)]">
            {firstLine(errorMsg)}
          </div>
          <details className="mt-1 text-[10px] text-[color:var(--color-penumbra-muted)]">
            <summary className="cursor-pointer">full traceback</summary>
            <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] text-[color:var(--color-penumbra-muted)]">
              {errorMsg}
            </pre>
          </details>
        </div>
      )}

      {lastResult && (
        <div className="space-y-2">
          <div className="grid grid-cols-3 gap-2 text-[10px]">
            <Stat label="registered" value={lastResult.name ?? "—"} accent />
            <Stat label="scope" value={lastResult.scope ?? "—"} />
            <Stat label="src chars" value={lastResult.source_chars ?? 0} digits={0} />
            <Stat
              label="try.ok"
              value={lastResult.try?.ok ? "yes" : "no"}
              accent={lastResult.try?.ok}
              ember={!lastResult.try?.ok}
            />
            <Stat label="try.result" value={lastResult.try?.result ?? "—"} />
          </div>
          {lastResult.try?.error && (
            <div className="border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-2 py-2 text-[10px] text-[color:var(--color-penumbra-ember)]">
              <div className="font-semibold uppercase tracking-wider">smoke run failed</div>
              <div className="mt-1 text-[11px] text-[color:var(--color-penumbra-text)]">
                {firstLine(lastResult.try.error)}
              </div>
              <details className="mt-1 text-[10px] text-[color:var(--color-penumbra-muted)]">
                <summary className="cursor-pointer">full traceback</summary>
                <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] text-[color:var(--color-penumbra-muted)]">
                  {lastResult.try.error}
                </pre>
              </details>
            </div>
          )}
        </div>
      )}

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          registered ({policies.length})
        </div>
        {policies.length === 0 ? (
          <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">none yet</div>
        ) : (
          <table className="w-full text-[10px]">
            <thead className="text-[color:var(--color-penumbra-dim)]">
              <tr>
                <th className="text-left font-normal">name</th>
                <th className="text-left font-normal">scope</th>
                <th className="text-left font-normal">src chars</th>
                <th className="text-right font-normal" />
              </tr>
            </thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.name} className="border-t border-[color:var(--color-penumbra-border)]">
                  <td className="py-1 text-[color:var(--color-penumbra-text)]">{p.name}</td>
                  <td className="py-1 text-[color:var(--color-penumbra-muted)]">{p.scope}</td>
                  <td className="py-1 tabular-nums text-[color:var(--color-penumbra-muted)]">
                    {p.source_chars}
                  </td>
                  <td className="py-1 text-right">
                    <button
                      type="button"
                      onClick={() => void remove(p.name)}
                      disabled={busy}
                      className="border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-2 py-0.5 text-[9px] uppercase text-[color:var(--color-penumbra-ember)] disabled:opacity-50"
                    >
                      drop
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
