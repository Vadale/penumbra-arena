/**
 * Configuration editor page (Wave 1A frontend).
 *
 * Drives the `GET /config` + `POST /config` endpoint pair from the
 * browser. The page is split into three cards:
 *  - Runtime parameters (mutable live) — tick rate + reward weights
 *    + DP epsilon budget.
 *  - Restart-required parameters — n_agents, match_max_ticks,
 *    k_anonymity_k. Each emits a copy-paste env-var line so the user
 *    can re-launch the orchestrator with the new value.
 *  - Read-only info — pty + MAPPO flags with a single caption
 *    explaining how to flip them.
 *
 * Each editable field owns its own draft state + Apply button + inline
 * status line. POST bodies contain ONLY the key being applied so the
 * backend can re-validate without coupling to the whole snapshot.
 */

import { type ChangeEvent, useCallback, useEffect, useState } from "react";
import { FetchError } from "../charts/_shared";
import { useFetchJsonOnce } from "../hooks/useFetchJson";

interface RewardWeights {
  dispatch_bonus: number;
  dispatch_penalty: number;
  fill_rate_bonus: number;
}

interface DefenseConfig {
  k_anonymity_k: number;
  dp_epsilon_budget: number;
}

interface ConfigPayload {
  n_agents: number;
  match_max_ticks: number;
  tick_hz: number;
  reward_weights: RewardWeights;
  defenses: DefenseConfig;
  pty_enabled: boolean;
  mappo_loaded: boolean;
}

interface ApplyResponse {
  applied: string[];
  restart_required: string[];
}

type ApplyStatus =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "applied" }
  | { kind: "restart"; envLine: string }
  | { kind: "error"; message: string };

const TICK_HZ_LADDER: readonly number[] = [0.5, 1, 2, 5, 10] as const;

/** Map a dotted config key to its PENUMBRA_* env var. */
function envVarName(key: string): string {
  const flat = key.replace(/\./g, "_").toUpperCase();
  return `PENUMBRA_${flat}`;
}

function formatEnvValue(value: number | string | boolean): string {
  if (typeof value === "boolean") return value ? "1" : "0";
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toFixed(0) : String(value);
  }
  return value;
}

async function postConfig(
  key: string,
  value: number | string | boolean,
): Promise<ApplyResponse | { error: string }> {
  try {
    const flat = buildFlatBody(key, value);
    const res = await fetch("/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(flat),
    });
    if (!res.ok) {
      const text = await res.text();
      return { error: `HTTP ${res.status}: ${text.slice(0, 160)}` };
    }
    return (await res.json()) as ApplyResponse;
  } catch (exc) {
    return { error: exc instanceof Error ? exc.message : "request failed" };
  }
}

function buildFlatBody(key: string, value: number | string | boolean): Record<string, unknown> {
  if (!key.includes(".")) return { [key]: value };
  const [head, ...rest] = key.split(".");
  let inner: Record<string, unknown> = { [rest[rest.length - 1] as string]: value };
  for (let i = rest.length - 2; i >= 0; i -= 1) {
    const k = rest[i] as string;
    inner = { [k]: inner };
  }
  return { [head as string]: inner };
}

export function Config() {
  const state = useFetchJsonOnce<ConfigPayload>("/config");

  return (
    <div className="flex h-full flex-col bg-[color:var(--color-penumbra-bg)] text-[color:var(--color-penumbra-text)]">
      <header className="flex items-center justify-between border-b border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] px-4 py-2">
        <div className="flex items-baseline gap-3">
          <a
            href="/"
            className="text-sm font-semibold tracking-tight text-[color:var(--color-penumbra-text)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            penumbra
          </a>
          <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-muted)]">
            configuration
          </span>
        </div>
        <nav className="flex items-center gap-2 text-[11px]">
          <a
            href="/bench"
            className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            bench
          </a>
          <a
            href="/operator"
            className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            operator
          </a>
          <a
            href="/"
            className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            dashboard →
          </a>
        </nav>
      </header>

      <main className="flex-1 overflow-auto px-4 py-3 font-mono text-[11px]">
        {state.kind === "loading" && (
          <div className="text-[color:var(--color-penumbra-muted)]">loading /config…</div>
        )}
        {state.kind === "error" && <FetchError message={state.message} />}
        {state.kind === "data" && <ConfigBody initial={state.value} />}
      </main>
    </div>
  );
}

function ConfigBody({ initial }: { initial: ConfigPayload }) {
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
      <RuntimeSection initial={initial} />
      <RestartSection initial={initial} />
      <ReadOnlySection initial={initial} />
    </div>
  );
}

function SectionShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section
      aria-label={title}
      className="flex flex-col gap-2 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] p-3"
    >
      <header className="flex items-baseline justify-between">
        <h2 className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-dim)]">
          {title}
        </h2>
        <span className="text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
          {subtitle}
        </span>
      </header>
      <div className="flex flex-col gap-3">{children}</div>
    </section>
  );
}

function RuntimeSection({ initial }: { initial: ConfigPayload }) {
  return (
    <SectionShell title="Runtime parameters" subtitle="live · POST /config">
      <TickHzControl initialValue={initial.tick_hz} />
      <NumberField
        configKey="reward_weights.dispatch_bonus"
        label="reward · dispatch bonus"
        initialValue={initial.reward_weights.dispatch_bonus}
        min={-100}
        max={100}
        step={0.5}
      />
      <NumberField
        configKey="reward_weights.dispatch_penalty"
        label="reward · dispatch penalty"
        initialValue={initial.reward_weights.dispatch_penalty}
        min={-100}
        max={100}
        step={0.5}
      />
      <NumberField
        configKey="reward_weights.fill_rate_bonus"
        label="reward · fill-rate bonus"
        initialValue={initial.reward_weights.fill_rate_bonus}
        min={-100}
        max={100}
        step={0.5}
      />
      <NumberField
        configKey="defenses.dp_epsilon_budget"
        label="defenses · dp epsilon budget"
        initialValue={initial.defenses.dp_epsilon_budget}
        min={0.1}
        max={100}
        step={0.1}
      />
    </SectionShell>
  );
}

function RestartSection({ initial }: { initial: ConfigPayload }) {
  return (
    <SectionShell title="Restart-required parameters" subtitle="restart to apply">
      <RestartField
        configKey="n_agents"
        label="n agents"
        initialValue={initial.n_agents}
        min={10}
        max={100}
        step={1}
      />
      <RestartField
        configKey="match_max_ticks"
        label="match max ticks"
        initialValue={initial.match_max_ticks}
        min={100}
        max={5000}
        step={100}
      />
      <RestartField
        configKey="defenses.k_anonymity_k"
        label="defenses · k-anonymity k"
        initialValue={initial.defenses.k_anonymity_k}
        min={1}
        max={20}
        step={1}
      />
    </SectionShell>
  );
}

function ReadOnlySection({ initial }: { initial: ConfigPayload }) {
  return (
    <SectionShell title="Read-only info" subtitle="boot-time flags">
      <Badge label="pty_enabled" on={initial.pty_enabled} onLabel="enabled" offLabel="disabled" />
      <Badge
        label="mappo_loaded"
        on={initial.mappo_loaded}
        onLabel="loaded"
        offLabel="random_walk"
      />
      <p className="text-[10px] leading-snug text-[color:var(--color-penumbra-muted)]">
        Set <code className="text-[color:var(--color-penumbra-cyan)]">PENUMBRA_ENABLE_PTY=1</code>{" "}
        and{" "}
        <code className="text-[color:var(--color-penumbra-cyan)]">
          PENUMBRA_MAPPO_CHECKPOINT=&lt;path&gt;
        </code>{" "}
        before starting the server to change these.
      </p>
    </SectionShell>
  );
}

function Badge({
  label,
  on,
  onLabel,
  offLabel,
}: {
  label: string;
  on: boolean;
  onLabel: string;
  offLabel: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </span>
      <span
        className={
          on
            ? "rounded-sm border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]"
            : "rounded-sm border border-[color:var(--color-penumbra-border)] px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]"
        }
      >
        {on ? onLabel : offLabel}
      </span>
    </div>
  );
}

function StatusLine({ status }: { status: ApplyStatus }) {
  if (status.kind === "idle") return null;
  if (status.kind === "submitting") {
    return (
      <span className="text-[10px] text-[color:var(--color-penumbra-muted)]">submitting…</span>
    );
  }
  if (status.kind === "applied") {
    return <span className="text-[10px] text-[color:var(--color-penumbra-cyan)]">applied</span>;
  }
  if (status.kind === "error") {
    return (
      <span className="text-[10px] text-[color:var(--color-penumbra-ember)]">{status.message}</span>
    );
  }
  return null;
}

function NumberField({
  configKey,
  label,
  initialValue,
  min,
  max,
  step,
}: {
  configKey: string;
  label: string;
  initialValue: number;
  min: number;
  max: number;
  step: number;
}) {
  const [current, setCurrent] = useState<number>(initialValue);
  const [draft, setDraft] = useState<string>(String(initialValue));
  const [status, setStatus] = useState<ApplyStatus>({ kind: "idle" });

  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    setDraft(event.target.value);
  };

  const onApply = useCallback(async () => {
    const parsed = Number(draft);
    if (!Number.isFinite(parsed)) {
      setStatus({ kind: "error", message: "not a number" });
      return;
    }
    if (parsed < min || parsed > max) {
      setStatus({ kind: "error", message: `out of range [${min}, ${max}]` });
      return;
    }
    setStatus({ kind: "submitting" });
    const result = await postConfig(configKey, parsed);
    if ("error" in result) {
      setStatus({ kind: "error", message: result.error });
      return;
    }
    setCurrent(parsed);
    setStatus({ kind: "applied" });
  }, [draft, configKey, min, max]);

  return (
    <div className="flex flex-col gap-1">
      <label className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          {label}
        </span>
        <span className="text-[9px] text-[color:var(--color-penumbra-muted)]">
          current: {String(current)}
        </span>
      </label>
      <div className="flex items-center gap-2">
        <input
          aria-label={configKey}
          type="number"
          value={draft}
          onChange={onChange}
          min={min}
          max={max}
          step={step}
          className="w-32 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <button
          type="button"
          onClick={() => void onApply()}
          disabled={status.kind === "submitting"}
          className="rounded-sm border border-[color:var(--color-penumbra-cyan)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] hover:bg-[color:var(--color-penumbra-cyan-bg)] disabled:opacity-40"
        >
          apply
        </button>
        <StatusLine status={status} />
      </div>
    </div>
  );
}

function TickHzControl({ initialValue }: { initialValue: number }) {
  const [current, setCurrent] = useState<number>(initialValue);
  const [draft, setDraft] = useState<number>(initialValue);
  const [status, setStatus] = useState<ApplyStatus>({ kind: "idle" });

  const onApply = useCallback(async () => {
    setStatus({ kind: "submitting" });
    const result = await postConfig("tick_hz", draft);
    if ("error" in result) {
      setStatus({ kind: "error", message: result.error });
      return;
    }
    setCurrent(draft);
    setStatus({ kind: "applied" });
  }, [draft]);

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          tick hz
        </span>
        <span className="text-[9px] text-[color:var(--color-penumbra-muted)]">
          current: {current} Hz
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        <fieldset
          aria-label="tick_hz"
          className="flex items-center gap-1 rounded-sm border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1.5 py-0.5"
        >
          {TICK_HZ_LADDER.map((hz) => {
            const active = Math.abs(draft - hz) < 1e-6;
            return (
              <button
                key={hz}
                type="button"
                onClick={() => setDraft(hz)}
                aria-pressed={active}
                className={
                  active
                    ? "border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-1.5 py-0.5 text-[10px] tabular-nums uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]"
                    : "border border-[color:var(--color-penumbra-border)] px-1.5 py-0.5 text-[10px] tabular-nums uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-text)]"
                }
              >
                {hz}x
              </button>
            );
          })}
        </fieldset>
        <button
          type="button"
          onClick={() => void onApply()}
          disabled={status.kind === "submitting"}
          className="rounded-sm border border-[color:var(--color-penumbra-cyan)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] hover:bg-[color:var(--color-penumbra-cyan-bg)] disabled:opacity-40"
        >
          apply
        </button>
        <StatusLine status={status} />
      </div>
    </div>
  );
}

function CopyEnvButton({ envLine }: { envLine: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const handle = window.setTimeout(() => setCopied(false), 1500);
    return () => window.clearTimeout(handle);
  }, [copied]);

  const onCopy = useCallback(async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(envLine);
      } else {
        // Headless / insecure-origin fallback: a transient textarea + execCommand.
        const ta = document.createElement("textarea");
        ta.value = envLine;
        ta.setAttribute("readonly", "");
        ta.style.position = "absolute";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }, [envLine]);

  return (
    <button
      type="button"
      onClick={() => void onCopy()}
      className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:border-[color:var(--color-penumbra-cyan)] hover:text-[color:var(--color-penumbra-cyan)]"
    >
      {copied ? "copied!" : "copy env line"}
    </button>
  );
}

function RestartField({
  configKey,
  label,
  initialValue,
  min,
  max,
  step,
}: {
  configKey: string;
  label: string;
  initialValue: number;
  min: number;
  max: number;
  step: number;
}) {
  const [draft, setDraft] = useState<string>(String(initialValue));
  const [status, setStatus] = useState<ApplyStatus>({ kind: "idle" });

  const onChange = (event: ChangeEvent<HTMLInputElement>) => {
    setDraft(event.target.value);
  };

  const onApply = useCallback(async () => {
    const parsed = Number(draft);
    if (!Number.isFinite(parsed)) {
      setStatus({ kind: "error", message: "not a number" });
      return;
    }
    if (parsed < min || parsed > max) {
      setStatus({ kind: "error", message: `out of range [${min}, ${max}]` });
      return;
    }
    setStatus({ kind: "submitting" });
    const result = await postConfig(configKey, parsed);
    if ("error" in result) {
      setStatus({ kind: "error", message: result.error });
      return;
    }
    if (result.restart_required.length > 0) {
      const envLine = `${envVarName(configKey)}=${formatEnvValue(parsed)}`;
      setStatus({ kind: "restart", envLine });
    } else {
      setStatus({ kind: "applied" });
    }
  }, [draft, configKey, min, max]);

  return (
    <div className="flex flex-col gap-1">
      <label className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          {label}
        </span>
        <span className="text-[9px] text-[color:var(--color-penumbra-muted)]">
          current: {initialValue}
        </span>
      </label>
      <div className="flex items-center gap-2">
        <input
          aria-label={configKey}
          type="number"
          value={draft}
          onChange={onChange}
          min={min}
          max={max}
          step={step}
          className="w-32 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <button
          type="button"
          onClick={() => void onApply()}
          disabled={status.kind === "submitting"}
          className="rounded-sm border border-[color:var(--color-penumbra-cyan)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] hover:bg-[color:var(--color-penumbra-cyan-bg)] disabled:opacity-40"
        >
          apply
        </button>
        {status.kind !== "restart" && <StatusLine status={status} />}
      </div>
      {status.kind === "restart" && (
        <div
          role="alert"
          aria-label={`Restart required for ${configKey}`}
          className="flex flex-col gap-1 rounded-sm border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-2 py-1"
        >
          <span className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)]">
            restart server to apply
          </span>
          <code className="text-[10px] text-[color:var(--color-penumbra-text)] break-all">
            {status.envLine}
          </code>
          <div>
            <CopyEnvButton envLine={status.envLine} />
          </div>
        </div>
      )}
    </div>
  );
}
