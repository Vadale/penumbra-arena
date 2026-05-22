/**
 * Per-feature saliency for the MAPPO actor.
 *
 * For a chosen agent, computes ∂p(chosen_action)/∂x_i — the gradient
 * of the actor's chosen-action probability w.r.t. each observation
 * feature. The absolute value tells you which features moved the
 * policy the most.
 */

import { useEffect, useState } from "react";

interface SaliencyPayload {
  available: boolean;
  agent_id?: number;
  chosen_action?: number;
  features?: number[];
  feature_labels?: string[];
  saliency?: number[];
}

export function SaliencyChart() {
  const [agentId, setAgentId] = useState(0);
  const [data, setData] = useState<SaliencyPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    const grab = async () => {
      try {
        const res = await fetch(`/learning/saliency/${agentId}`);
        if (!res.ok) return;
        const payload = (await res.json()) as SaliencyPayload;
        if (!cancelled) setData(payload);
      } catch {}
    };
    void grab();
    const t = window.setInterval(grab, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [agentId]);

  if (!data || !data.available) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        saliency unavailable (MAPPO not loaded)
      </div>
    );
  }
  const labels = data.feature_labels ?? [];
  const features = data.features ?? [];
  const saliency = data.saliency ?? [];
  const maxSal = Math.max(...saliency, 1e-6);

  return (
    <div className="font-mono space-y-3">
      <div className="flex items-center gap-2 text-[10px]">
        <label className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          agent
        </label>
        <input
          type="number"
          min={0}
          max={49}
          value={agentId}
          onChange={(e) => setAgentId(Math.max(0, Math.min(49, Number(e.target.value))))}
          className="w-16 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <span className="text-[color:var(--color-penumbra-muted)]">
          chosen action = {data.chosen_action} · |∂p/∂x| max = {maxSal.toExponential(2)}
        </span>
      </div>

      <svg
        viewBox={`0 0 560 ${labels.length * 16 + 6}`}
        width="100%"
        role="img"
        aria-label="saliency bars"
      >
        {labels.map((label, i) => {
          const y = i * 16 + 4;
          const sal = saliency[i] ?? 0;
          const w = (sal / maxSal) * 380;
          const value = features[i] ?? 0;
          return (
            <g key={label}>
              <text
                x={6}
                y={y + 6}
                fontSize={9}
                dominantBaseline="central"
                fill="var(--color-penumbra-muted)"
              >
                {label}
              </text>
              <rect
                x={120}
                y={y}
                width={Math.max(1, w)}
                height={12}
                fill="var(--color-penumbra-cyan)"
                opacity={0.65}
              />
              <text
                x={124 + Math.max(1, w)}
                y={y + 6}
                fontSize={9}
                dominantBaseline="central"
                fill="var(--color-penumbra-text)"
              >
                |∂p/∂x| = {sal.toExponential(2)} · x = {value.toFixed(2)}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Computed via autograd on the actor's chosen-action probability. Higher bars = features the
        policy is currently most sensitive to.
      </div>
    </div>
  );
}
