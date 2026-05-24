/**
 * Per-agent policy entropy + critic value summary.
 *
 * For each live agent: which node it's on, the actor distribution
 * entropy (low = confident decision, high = uncertain), and the
 * top-action probability. The single critic V(state) for the whole
 * swarm is the headline number — that's the policy's expected
 * future return averaged over the agents.
 */

import { useFetchJsonPoll } from "../hooks/useFetchJson";
import { FetchError, Stat } from "./_shared";

interface AgentRow {
  agent_id: number;
  node: number;
  entropy: number;
  top_prob: number;
}
interface Payload {
  available: boolean;
  v_state?: number;
  per_agent?: AgentRow[];
  temperature?: number;
}

export function ValueMapChart() {
  // 4s cadence — value_estimate + per-agent action_probabilities is a heavy
  // PyTorch forward pass; slow the poll under stress.
  const state = useFetchJsonPoll<Payload>("/learning/value-map", 4000);
  const data =
    state.kind === "data" ? state.value : state.kind === "error" ? state.lastValue : undefined;

  if (!data?.available || !data.per_agent) {
    if (state.kind === "error") return <FetchError message={state.message} />;
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        value map unavailable (MAPPO not loaded)
      </div>
    );
  }
  const rows = data.per_agent;
  const maxEntropy = Math.log(7);
  const entropies = rows.map((r) => r.entropy);
  const meanEntropy = entropies.reduce((s, v) => s + v, 0) / Math.max(rows.length, 1);
  const topProbs = rows.map((r) => r.top_prob);
  const meanTop = topProbs.reduce((s, v) => s + v, 0) / Math.max(rows.length, 1);

  // Group by node so the histogram is per-node not per-agent.
  const byNode = new Map<number, { entropy: number; count: number }>();
  for (const r of rows) {
    const cur = byNode.get(r.node) ?? { entropy: 0, count: 0 };
    cur.entropy += r.entropy;
    cur.count += 1;
    byNode.set(r.node, cur);
  }
  const nodeEntries = Array.from(byNode.entries())
    .map(([node, agg]) => ({ node, avgEntropy: agg.entropy / agg.count, count: agg.count }))
    .sort((a, b) => a.node - b.node);

  return (
    <div className="font-mono space-y-3">
      {state.kind === "error" && <FetchError message={state.message} />}
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat
          label="V(s)"
          value={(data.v_state ?? 0).toFixed(3)}
          accent
          caption="critic estimate"
        />
        <Stat
          label="mean entropy"
          value={meanEntropy.toFixed(3)}
          accent={meanEntropy < 1.0}
          ember={meanEntropy >= 1.5}
          caption={`/ ${maxEntropy.toFixed(2)} max`}
        />
        <Stat
          label="mean top-prob"
          value={`${(meanTop * 100).toFixed(1)}%`}
          accent
          caption="actor confidence"
        />
        <Stat label="T" value={(data.temperature ?? 1).toFixed(2)} caption="sampling temp" />
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          per-node average entropy (cyan = confident, ember = uncertain)
        </div>
        <svg
          viewBox={`0 0 560 ${nodeEntries.length * 18 + 6}`}
          width="100%"
          role="img"
          aria-label="per-node entropy"
        >
          {nodeEntries.map((n) => {
            const y = nodeEntries.indexOf(n) * 18 + 4;
            const ratio = Math.min(1, n.avgEntropy / maxEntropy);
            const w = ratio * 420;
            return (
              <g key={`node-${n.node}`}>
                <text
                  x={6}
                  y={y + 6}
                  fontSize={9}
                  dominantBaseline="central"
                  fill="var(--color-penumbra-muted)"
                >
                  #{n.node} · {n.count}a
                </text>
                <rect
                  x={80}
                  y={y}
                  width={Math.max(2, w)}
                  height={12}
                  fill={
                    ratio > 0.7
                      ? "color-mix(in srgb, var(--color-penumbra-ember) 55%, transparent)"
                      : "color-mix(in srgb, var(--color-penumbra-cyan) 55%, transparent)"
                  }
                  stroke={
                    ratio > 0.7 ? "var(--color-penumbra-ember)" : "var(--color-penumbra-cyan)"
                  }
                  strokeWidth={0.7}
                />
                <text
                  x={84 + Math.max(2, w)}
                  y={y + 6}
                  fontSize={9}
                  dominantBaseline="central"
                  fill="var(--color-penumbra-text)"
                >
                  {n.avgEntropy.toFixed(3)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
