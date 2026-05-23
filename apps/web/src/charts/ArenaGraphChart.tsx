/**
 * Force-directed 2D arena graph.
 *
 * Cytoscape would be the natural choice but we already have all the
 * data; a simple SVG with a Fruchterman-Reingold-style layout (one
 * relaxation pass) is enough for ~50 nodes and 0 external deps.
 */

import { useEffect, useMemo, useState } from "react";
import { Stat } from "./_shared";

interface Topology {
  nodes: number[];
  edges: { u: number; v: number; cost: number }[];
  goals: number[];
}

const WIDTH = 560;
const HEIGHT = 460;

function layout(topology: Topology): Map<number, { x: number; y: number }> {
  const positions = new Map<number, { x: number; y: number }>();
  const nodes = topology.nodes;
  const n = nodes.length;
  // Circle-pack initial seed.
  nodes.forEach((id, i) => {
    const theta = (i / n) * 2 * Math.PI;
    positions.set(id, {
      x: WIDTH / 2 + (Math.min(WIDTH, HEIGHT) / 2 - 30) * Math.cos(theta),
      y: HEIGHT / 2 + (Math.min(WIDTH, HEIGHT) / 2 - 30) * Math.sin(theta),
    });
  });
  // 80 iterations of spring-electrical relaxation.
  const k = Math.sqrt((WIDTH * HEIGHT) / Math.max(n, 1));
  for (let iter = 0; iter < 80; iter += 1) {
    const cooling = 1 - iter / 80;
    const disp = new Map<number, { dx: number; dy: number }>();
    nodes.forEach((id) => disp.set(id, { dx: 0, dy: 0 }));
    // Repulsion.
    for (let i = 0; i < n; i += 1) {
      for (let j = i + 1; j < n; j += 1) {
        const a = positions.get(nodes[i] ?? -1);
        const b = positions.get(nodes[j] ?? -1);
        if (!a || !b) continue;
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const d = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01);
        const f = (k * k) / d / d;
        const ad = disp.get(nodes[i] ?? -1);
        const bd = disp.get(nodes[j] ?? -1);
        if (ad) {
          ad.dx += (dx / d) * f;
          ad.dy += (dy / d) * f;
        }
        if (bd) {
          bd.dx -= (dx / d) * f;
          bd.dy -= (dy / d) * f;
        }
      }
    }
    // Attraction (springs).
    for (const e of topology.edges) {
      const a = positions.get(e.u);
      const b = positions.get(e.v);
      if (!a || !b) continue;
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const d = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01);
      const f = (d * d) / k;
      const ad = disp.get(e.u);
      const bd = disp.get(e.v);
      if (ad) {
        ad.dx -= (dx / d) * f;
        ad.dy -= (dy / d) * f;
      }
      if (bd) {
        bd.dx += (dx / d) * f;
        bd.dy += (dy / d) * f;
      }
    }
    // Move + cap by temperature.
    for (const id of nodes) {
      const p = positions.get(id);
      const d = disp.get(id);
      if (!p || !d) continue;
      const m = Math.sqrt(d.dx * d.dx + d.dy * d.dy);
      const cap = Math.max(cooling * 12, 0.5);
      const s = Math.min(m, cap);
      p.x = Math.max(20, Math.min(WIDTH - 20, p.x + (d.dx / Math.max(m, 0.01)) * s));
      p.y = Math.max(20, Math.min(HEIGHT - 20, p.y + (d.dy / Math.max(m, 0.01)) * s));
    }
  }
  return positions;
}

export function ArenaGraphChart() {
  const [topology, setTopology] = useState<Topology | null>(null);
  useEffect(() => {
    let cancelled = false;
    const grab = async () => {
      try {
        const res = await fetch("/arena/topology");
        if (!res.ok) return;
        const payload = (await res.json()) as Topology;
        if (!cancelled) setTopology(payload);
      } catch {}
    };
    void grab();
    const t = window.setInterval(grab, 6000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  const positions = useMemo(
    () => (topology ? layout(topology) : new Map<number, { x: number; y: number }>()),
    [topology],
  );

  if (!topology) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        loading arena…
      </div>
    );
  }

  const maxCost = Math.max(...topology.edges.map((e) => e.cost), 1);

  return (
    <div className="font-mono space-y-2">
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="nodes" value={String(topology.nodes.length)} accent />
        <Stat label="edges" value={String(topology.edges.length)} accent />
        <Stat label="goals" value={String(topology.goals.length)} accent />
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
        role="img"
        aria-label="force-directed arena graph"
      >
        {topology.edges.map((e) => {
          const a = positions.get(e.u);
          const b = positions.get(e.v);
          if (!a || !b) return null;
          const intensity = e.cost / maxCost;
          return (
            <line
              key={`e-${e.u}-${e.v}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="var(--color-penumbra-cyan)"
              strokeWidth={0.4 + intensity * 1.4}
              opacity={0.3 + intensity * 0.5}
            />
          );
        })}
        {topology.nodes.map((id) => {
          const p = positions.get(id);
          if (!p) return null;
          const isGoal = topology.goals.includes(id);
          return (
            <g key={`n-${id}`}>
              <circle
                cx={p.x}
                cy={p.y}
                r={isGoal ? 6 : 4}
                fill={isGoal ? "var(--color-penumbra-ember)" : "var(--color-penumbra-cyan)"}
                opacity={0.85}
                stroke="var(--color-penumbra-bg)"
                strokeWidth={1.2}
              />
              <text x={p.x + 7} y={p.y + 3} fontSize={8} fill="var(--color-penumbra-muted)">
                {id}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Fruchterman-Reingold layout, 80 relaxation iterations. Ember nodes = goals; edge thickness ∝
        cost. Layout recomputed every 6s as the arena topology mutates.
      </div>
    </div>
  );
}
