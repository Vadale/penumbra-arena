/**
 * World view — individual agents on a stable graph layout.
 *
 * Where `Arena2D` shows the topology as an aggregate (one badge
 * with N agents per node), `WorldView` renders every agent as a
 * SEPARATE glyph that animates smoothly from its previous position
 * to its current one each tick.
 *
 * Design choices
 * - Layout is force-directed but FROZEN after warm-up so the world
 *   feels stable. The same node is at the same place across reloads
 *   (we keep positions in a Map keyed by node id).
 * - Each agent: a colored circle, hue derived from id (golden-ratio
 *   spread for colourblind separation), 6 px radius.
 * - Multiple agents at the same node: arranged on a small ring
 *   around the node centre (no overlap, no number-only summary).
 * - Goals: outer luminous ring + label "goal N" + slight glow.
 * - Edges: rendered first (behind), opacity scaled by cost cyan→ember.
 * - Animation: 250 ms CSS transform transition on each agent.
 */

import * as d3 from "d3";
import { useEffect, useMemo, useState } from "react";
import { usePenumbraStore } from "../streams/store";
import { useArenaTopology } from "../streams/topology";

interface NodePosition {
  x: number;
  y: number;
}

interface NodeDatum extends d3.SimulationNodeDatum {
  id: number;
}

interface LinkDatum extends d3.SimulationLinkDatum<NodeDatum> {
  cost: number;
}

const WIDTH = 900;
const HEIGHT = 540;
const FORCE_LINK_DISTANCE = 70;
const FORCE_CHARGE = -200;
const AGENT_RADIUS = 4.5;
const AGENT_ORBIT_RADIUS = 10;
const NODE_RADIUS = 7;
const GOAL_RING_RADIUS = 14;

/** Stable hue per agent id; golden-ratio spread for colourblind separation. */
function agentColor(id: number): string {
  const hue = ((id * 0.6180339887) % 1) * 360;
  return `oklch(0.78 0.16 ${hue.toFixed(1)})`;
}

/** Position N agents on a small ring around a node centre. */
function orbitPosition(index: number, total: number, cx: number, cy: number): NodePosition {
  if (total === 1) return { x: cx, y: cy };
  const angle = (index / total) * Math.PI * 2;
  return {
    x: cx + AGENT_ORBIT_RADIUS * Math.cos(angle),
    y: cy + AGENT_ORBIT_RADIUS * Math.sin(angle),
  };
}

export function WorldView() {
  const topology = useArenaTopology();
  const lastFrame = usePenumbraStore((s) => s.lastFrame);
  const [positions, setPositions] = useState<Map<number, NodePosition>>(new Map());

  // Run a force simulation once when topology arrives, then freeze.
  useEffect(() => {
    if (topology === null) return;

    const nodes: NodeDatum[] = topology.nodes.map((id) => ({ id }));
    const links: LinkDatum[] = topology.edges.map((e) => ({
      source: e.u,
      target: e.v,
      cost: e.cost,
    }));

    const sim = d3
      .forceSimulation<NodeDatum, LinkDatum>(nodes)
      .force(
        "link",
        d3
          .forceLink<NodeDatum, LinkDatum>(links)
          .id((n) => n.id)
          .distance(FORCE_LINK_DISTANCE)
          .strength(0.6),
      )
      .force("charge", d3.forceManyBody<NodeDatum>().strength(FORCE_CHARGE))
      .force("center", d3.forceCenter(WIDTH / 2, HEIGHT / 2))
      .force("collide", d3.forceCollide<NodeDatum>().radius(GOAL_RING_RADIUS + 6))
      .stop();

    // Tick to convergence (~300 iterations is enough for 50 nodes).
    for (let i = 0; i < 300; i++) sim.tick();

    const newPositions = new Map<number, NodePosition>();
    for (const n of sim.nodes()) {
      newPositions.set(n.id, { x: n.x ?? WIDTH / 2, y: n.y ?? HEIGHT / 2 });
    }
    setPositions(newPositions);
  }, [topology]);

  // Compute per-agent rendering positions from the live frame.
  const agentPlacements = useMemo(() => {
    if (lastFrame === null) return [] as { id: number; x: number; y: number }[];
    // Group agents by node, then orbit them around the node.
    const byNode = new Map<number, number[]>();
    for (const [idStr, nodeId] of Object.entries(lastFrame.agent_positions)) {
      const aid = Number(idStr);
      const arr = byNode.get(nodeId) ?? [];
      arr.push(aid);
      byNode.set(nodeId, arr);
    }
    const out: { id: number; x: number; y: number }[] = [];
    for (const [nodeId, agentIds] of byNode.entries()) {
      const np = positions.get(nodeId);
      if (np === undefined) continue;
      const sorted = [...agentIds].sort((a, b) => a - b);
      for (let i = 0; i < sorted.length; i++) {
        const aid = sorted[i] as number;
        const p = orbitPosition(i, sorted.length, np.x, np.y);
        out.push({ id: aid, x: p.x, y: p.y });
      }
    }
    return out;
  }, [lastFrame, positions]);

  // Edge color scale based on current OU costs.
  const colorScale = useMemo(() => {
    if (topology === null) return null;
    const costs = topology.edges.map((e) => e.cost);
    return d3
      .scaleLinear<string>()
      .domain([Math.min(...costs), Math.max(...costs)])
      .range([
        "color-mix(in srgb, var(--color-penumbra-cyan) 60%, transparent)",
        "color-mix(in srgb, var(--color-penumbra-ember) 60%, transparent)",
      ])
      .clamp(true);
  }, [topology]);

  if (topology === null || positions.size === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
        world layout warming up<span className="animate-pulse">…</span>
      </div>
    );
  }

  const goalSet = new Set(topology.goals);

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="h-full w-full"
      role="img"
      aria-label="Penumbra world view"
    >
      {/* edges behind everything */}
      <g data-edges>
        {topology.edges.map((e) => {
          const a = positions.get(e.u);
          const b = positions.get(e.v);
          if (a === undefined || b === undefined || colorScale === null) return null;
          return (
            <line
              key={`${e.u}-${e.v}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={colorScale(e.cost)}
              strokeWidth={1.1}
              strokeOpacity={0.8}
            />
          );
        })}
      </g>

      {/* nodes (small "city" markers) */}
      <g data-nodes>
        {topology.nodes.map((nodeId) => {
          const p = positions.get(nodeId);
          if (p === undefined) return null;
          const isGoal = goalSet.has(nodeId);
          return (
            <g key={nodeId} transform={`translate(${p.x},${p.y})`}>
              {isGoal && (
                <>
                  <circle
                    r={GOAL_RING_RADIUS}
                    fill="none"
                    stroke="var(--color-penumbra-cyan)"
                    strokeWidth={1.2}
                    strokeDasharray="3 3"
                    opacity={0.85}
                  />
                  <text
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={8}
                    y={GOAL_RING_RADIUS + 8}
                    fill="var(--color-penumbra-cyan)"
                    style={{ fontFamily: "var(--font-mono)" }}
                  >
                    goal {nodeId}
                  </text>
                </>
              )}
              <circle
                r={NODE_RADIUS}
                fill={isGoal ? "var(--color-penumbra-cyan-bg)" : "var(--color-penumbra-panel)"}
                stroke="var(--color-penumbra-border)"
                strokeWidth={0.7}
              />
              <text
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={7}
                fill="var(--color-penumbra-dim)"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {nodeId}
              </text>
            </g>
          );
        })}
      </g>

      {/* agents — every one a separate, animated glyph */}
      <g data-agents>
        {agentPlacements.map(({ id, x, y }) => (
          <circle
            key={id}
            cx={x}
            cy={y}
            r={AGENT_RADIUS}
            fill={agentColor(id)}
            stroke="var(--color-penumbra-bg)"
            strokeWidth={0.7}
            style={{
              transition: "cx 280ms ease-out, cy 280ms ease-out",
            }}
          >
            <title>agent {id}</title>
          </circle>
        ))}
      </g>
    </svg>
  );
}
