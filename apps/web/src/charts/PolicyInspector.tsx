/**
 * Click an agent (or pick by id) → see the MAPPO actor's reasoning.
 *
 * Shows the live observation features, the actor's action probability
 * distribution (bar chart), the chosen action highlighted, and the
 * agent's current node. The temperature is applied — same flow the
 * simulation uses for inference.
 */

import { useEffect, useState } from "react";
import { fetchPolicy, type PolicyInspection } from "../streams/learning";

interface Props {
  initialAgent?: number;
  nAgents?: number;
}

export function PolicyInspector({ initialAgent = 0, nAgents = 50 }: Props) {
  const [agentId, setAgentId] = useState(initialAgent);
  const [data, setData] = useState<PolicyInspection | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      setLoading(true);
      const res = await fetchPolicy(agentId);
      if (!cancelled) {
        setData(res);
        setLoading(false);
      }
    };
    void tick();
    // 2s — actor forward pass per poll; 800ms burned MPS for no gain.
    const t = window.setInterval(tick, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [agentId]);

  if (!data?.available) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        {data?.reason ?? "MAPPO not loaded — set PENUMBRA_MAPPO_CHECKPOINT and restart."}
      </div>
    );
  }

  const probs = data.action_probabilities ?? [];
  const labels = data.action_labels ?? [];
  const chosen = data.chosen_action ?? -1;
  const maxProb = Math.max(...probs, 1e-6);

  return (
    <div className="font-mono space-y-3">
      <div className="flex items-center gap-2">
        <label className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          agent
        </label>
        <input
          type="number"
          min={0}
          max={nAgents - 1}
          value={agentId}
          onChange={(e) => {
            const v = Number(e.target.value);
            if (Number.isFinite(v)) setAgentId(Math.max(0, Math.min(nAgents - 1, v)));
          }}
          className="w-16 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
        />
        <span className="text-[10px] text-[color:var(--color-penumbra-dim)]">
          at #{data.current_node} · temp {data.temperature?.toFixed(2)} ·{" "}
          {data.enabled ? "MAPPO" : "RANDOM"}
        </span>
        {loading && <span className="text-[9px] text-[color:var(--color-penumbra-dim)]">…</span>}
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          action probabilities (softmax(logits/T))
        </div>
        <svg
          viewBox={`0 0 560 ${probs.length * 22 + 8}`}
          width="100%"
          role="img"
          aria-label="action probability bars"
        >
          {probs.map((p, i) => {
            const y = i * 22 + 4;
            const w = (p / maxProb) * 380;
            const isChosen = i === chosen;
            return (
              <g key={labels[i] ?? `a-${i}`}>
                <text
                  x={6}
                  y={y + 11}
                  fontSize={10}
                  dominantBaseline="central"
                  fill={isChosen ? "var(--color-penumbra-cyan)" : "var(--color-penumbra-muted)"}
                >
                  {labels[i] ?? `a${i}`}
                </text>
                <rect
                  x={90}
                  y={y}
                  width={Math.max(2, w)}
                  height={16}
                  fill={
                    isChosen
                      ? "color-mix(in srgb, var(--color-penumbra-cyan) 70%, transparent)"
                      : "color-mix(in srgb, var(--color-penumbra-cyan) 22%, transparent)"
                  }
                  stroke="var(--color-penumbra-cyan)"
                  strokeWidth={isChosen ? 1.4 : 0.6}
                />
                <text
                  x={94 + Math.max(2, w)}
                  y={y + 11}
                  fontSize={10}
                  dominantBaseline="central"
                  fill="var(--color-penumbra-text)"
                >
                  {(p * 100).toFixed(1)}%
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          observation features (cost, is_goal × K neighbours)
        </div>
        <div className="flex flex-wrap gap-1 text-[10px]">
          {(data.observation ?? []).map((v, i) => (
            <span
              key={`feat-${i}-${v.toFixed(3)}`}
              className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1.5 py-0.5 tabular-nums text-[color:var(--color-penumbra-muted)]"
            >
              {v.toFixed(2)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
