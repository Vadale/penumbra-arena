/**
 * GATv2 attention visualizer.
 *
 * For every node in the arena, the GATv2 pathfinder computes a
 * softmax over its neighbours' compatibility scores. The heatmap
 * below shows, for a SELECTED source node, how much it attends to
 * each of its in-graph neighbours. The matrix is normalised row-wise
 * so each row sums to 1.0.
 */

import { useEffect, useMemo, useState } from "react";
import { Stat } from "./_shared";

interface AttentionPayload {
  available: boolean;
  n_nodes: number;
  node_ids: number[];
  goals: number[];
  values: number[];
  attention_layer1: number[][];
  attention_layer2: number[][];
}

export function GATAttentionChart() {
  const [data, setData] = useState<AttentionPayload | null>(null);
  const [selectedRow, setSelectedRow] = useState(0);
  const [layer, setLayer] = useState<"l1" | "l2">("l1");

  useEffect(() => {
    let cancelled = false;
    const grab = async () => {
      try {
        const res = await fetch("/learning/gat-attention");
        if (!res.ok) return;
        const payload = (await res.json()) as AttentionPayload;
        if (!cancelled) setData(payload);
      } catch {}
    };
    void grab();
    const t = window.setInterval(grab, 6000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  const row = useMemo(() => {
    if (!data) return null;
    const mat = layer === "l1" ? data.attention_layer1 : data.attention_layer2;
    return mat[selectedRow] ?? null;
  }, [data, layer, selectedRow]);

  if (!data) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        loading GATv2 attention…
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="nodes" value={String(data.n_nodes)} accent />
        <Stat label="goals" value={String(data.goals.length)} accent />
        <Stat label="layer" value={layer === "l1" ? "GAT layer 1" : "GAT layer 2"} />
        <div className="flex items-center justify-end gap-1">
          <button
            type="button"
            onClick={() => setLayer("l1")}
            className={
              layer === "l1"
                ? "border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-0.5 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)]"
                : "border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-[10px] uppercase text-[color:var(--color-penumbra-muted)]"
            }
          >
            L1
          </button>
          <button
            type="button"
            onClick={() => setLayer("l2")}
            className={
              layer === "l2"
                ? "border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-0.5 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)]"
                : "border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-[10px] uppercase text-[color:var(--color-penumbra-muted)]"
            }
          >
            L2
          </button>
        </div>
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          source node (row in the attention matrix)
        </div>
        <input
          type="range"
          min={0}
          max={Math.max(0, data.n_nodes - 1)}
          value={selectedRow}
          onChange={(e) => setSelectedRow(Number(e.target.value))}
          className="h-1 w-full accent-[color:var(--color-penumbra-cyan)]"
        />
        <div className="text-[10px] text-[color:var(--color-penumbra-muted)]">
          attending FROM node {data.node_ids[selectedRow]}
          {data.goals.includes(data.node_ids[selectedRow] ?? -1) && " (goal)"}
        </div>
      </div>

      {row && (
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
            attention weights to neighbours (row-normalised softmax)
          </div>
          <svg
            viewBox={`0 0 560 ${data.n_nodes * 7 + 6}`}
            width="100%"
            role="img"
            aria-label="attention row"
          >
            {row.map((alpha, j) => {
              if (alpha < 1e-6) return null;
              const y = j * 7 + 4;
              const w = Math.max(1, alpha * 420);
              const isSelf = j === selectedRow;
              const isGoal = data.goals.includes(data.node_ids[j] ?? -1);
              const color = isGoal
                ? "var(--color-penumbra-ember)"
                : isSelf
                  ? "color-mix(in srgb, var(--color-penumbra-cyan) 50%, white 20%)"
                  : "var(--color-penumbra-cyan)";
              return (
                <g key={`alpha-${j}-${alpha.toFixed(5)}`}>
                  <text
                    x={6}
                    y={y + 3}
                    fontSize={8}
                    dominantBaseline="central"
                    fill="var(--color-penumbra-muted)"
                  >
                    {data.node_ids[j]}
                  </text>
                  <rect x={40} y={y - 1} width={w} height={5} fill={color} opacity={0.85} />
                  <text
                    x={44 + w}
                    y={y + 3}
                    fontSize={8}
                    dominantBaseline="central"
                    fill="var(--color-penumbra-text)"
                  >
                    {(alpha * 100).toFixed(1)}%
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      )}

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        GATv2: e_ij = a · LeakyReLU(W₁ h_i + W₂ h_j) + α · cost_ij; α_ij = softmax over neighbours.
        Weights are RANDOM (untrained) — the panel shows the architecture, not learned policy.
      </div>
    </div>
  );
}
