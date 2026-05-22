/**
 * Multi-checkpoint A/B compare.
 *
 * Load a second MAPPO checkpoint into a side slot via
 * POST /learning/multi-checkpoint/{name}; then GET /learning/ab-compare
 * runs both policies over the live observations and reports KL
 * divergence + top-action agreement rate.
 */

import { useEffect, useState } from "react";

interface CompareData {
  available: boolean;
  reason?: string;
  n_agents?: number;
  agreement_rate?: number;
  mean_kl?: number;
  max_kl?: number;
  per_agent_kl?: number[];
}

export function MultiCheckpointChart() {
  const [data, setData] = useState<CompareData | null>(null);
  const [pickPath, setPickPath] = useState("mappo_v0.pt");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch(`/learning/multi-checkpoint/${pickPath}`, { method: "POST" });
      const payload = await res.json();
      setMessage(res.ok ? `loaded ${payload.path}` : `error: ${payload.detail ?? res.status}`);
    } catch (_e) {
      setMessage(`network error`);
    }
    setBusy(false);
  };

  useEffect(() => {
    let cancelled = false;
    const grab = async () => {
      try {
        const res = await fetch("/learning/ab-compare");
        if (!res.ok) return;
        const payload = (await res.json()) as CompareData;
        if (!cancelled) setData(payload);
      } catch {}
    };
    void grab();
    const t = window.setInterval(grab, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  return (
    <div className="font-mono space-y-3">
      <div className="flex items-center gap-2 text-[10px]">
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          load second checkpoint
        </label>
        <input
          value={pickPath}
          onChange={(e) => setPickPath(e.target.value)}
          className="w-40 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <button
          type="button"
          onClick={load}
          disabled={busy}
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-1 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
        >
          {busy ? "loading…" : "load"}
        </button>
        {message && (
          <span className="text-[10px] text-[color:var(--color-penumbra-muted)]">{message}</span>
        )}
      </div>

      {!data?.available ? (
        <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
          {data?.reason ?? "load a second checkpoint to start comparing"}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-2 text-[10px]">
            <Stat
              label="agreement"
              value={`${((data.agreement_rate ?? 0) * 100).toFixed(1)}%`}
              accent={(data.agreement_rate ?? 0) > 0.8}
              ember={(data.agreement_rate ?? 0) < 0.4}
            />
            <Stat
              label="mean KL"
              value={(data.mean_kl ?? 0).toFixed(4)}
              accent={(data.mean_kl ?? 0) < 0.5}
              ember={(data.mean_kl ?? 0) >= 1.0}
            />
            <Stat label="max KL" value={(data.max_kl ?? 0).toFixed(3)} />
            <Stat label="n agents" value={String(data.n_agents ?? 0)} />
          </div>

          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
              per-agent KL(primary‖second)
            </div>
            <svg
              viewBox={`0 0 560 ${(data.per_agent_kl ?? []).length * 8 + 6}`}
              width="100%"
              role="img"
              aria-label="per-agent KL"
            >
              {(data.per_agent_kl ?? []).map((kl, i) => {
                const max = Math.max(...(data.per_agent_kl ?? [1]), 1e-6);
                const y = i * 8 + 4;
                const w = (kl / max) * 480;
                return (
                  <g key={`kl-${i}-${kl.toFixed(4)}`}>
                    <text
                      x={6}
                      y={y + 3}
                      fontSize={8}
                      dominantBaseline="central"
                      fill="var(--color-penumbra-dim)"
                    >
                      a{i}
                    </text>
                    <rect
                      x={40}
                      y={y - 1}
                      width={Math.max(1, w)}
                      height={5}
                      fill={kl > 0.5 ? "var(--color-penumbra-ember)" : "var(--color-penumbra-cyan)"}
                      opacity={0.7}
                    />
                  </g>
                );
              })}
            </svg>
          </div>
        </>
      )}

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        KL(p‖q) = Σ p log(p/q) — asymmetric. Comparing the SAME checkpoint against itself gives KL ≈
        0 and agreement = 100%; that's a sanity check. Different training runs produce different
        policies → KL {">"} 0.
      </div>
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
  value: string;
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
