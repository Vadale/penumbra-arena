/**
 * Force-directed 2D arena view.
 *
 * Replaces the 3D circle-layout view that didn't show the graph
 * topology. Here the small-world structure of the Watts-Strogatz
 * arena is visible: hub nodes attract many short edges, "shortcut"
 * edges cross the layout, goals are marked with a luminous ring,
 * and each node's circle scales with the number of agents that
 * currently occupy it.
 *
 * Data sources
 * - `/arena/topology` (polled at ~4s): nodes + edges + edge costs +
 *   goals. The topology mutates slowly (OU drift + occasional
 *   weather event).
 * - WebSocket tick frames (10 Hz): agent positions. Used to compute
 *   the per-node occupancy and update node circles without restarting
 *   the force simulation.
 */

import * as d3 from "d3";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSelectedAgentStore } from "../stores/selectedAgent";
import { useEffectiveFrame } from "../streams/effectiveFrame";
import { useArenaTopology } from "../streams/topology";

type Tooltip =
  | { kind: "node"; id: number; count: number; x: number; y: number }
  | { kind: "edge"; u: number; v: number; cost: number; x: number; y: number };

interface NodeDatum extends d3.SimulationNodeDatum {
  id: number;
  isGoal: boolean;
}

interface LinkDatum extends d3.SimulationLinkDatum<NodeDatum> {
  cost: number;
}

const WIDTH = 800;
const HEIGHT = 520;
const FORCE_LINK_DISTANCE = 60;
const FORCE_CHARGE = -160;

export function Arena2D() {
  const topology = useArenaTopology();
  const lastFrame = useEffectiveFrame();
  const setSelectedAgentId = useSelectedAgentStore((s) => s.setSelectedAgentId);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const simulationRef = useRef<d3.Simulation<NodeDatum, LinkDatum> | null>(null);
  const nodeMapRef = useRef<Map<number, NodeDatum>>(new Map());
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);

  // Build / update the force simulation when topology arrives.
  useEffect(() => {
    if (topology === null || svgRef.current === null) return;

    const goalSet = new Set(topology.goals);
    const nodes: NodeDatum[] = topology.nodes.map((id) => {
      const existing = nodeMapRef.current.get(id);
      if (existing !== undefined) {
        existing.isGoal = goalSet.has(id);
        return existing;
      }
      const fresh: NodeDatum = { id, isGoal: goalSet.has(id) };
      nodeMapRef.current.set(id, fresh);
      return fresh;
    });
    // Drop nodes that no longer exist (rare but possible if weather
    // event removes all of a node's edges, leaving it orphan).
    const liveIds = new Set(topology.nodes);
    for (const stale of nodeMapRef.current.keys()) {
      if (!liveIds.has(stale)) nodeMapRef.current.delete(stale);
    }

    const links: LinkDatum[] = topology.edges.map((e) => ({
      source: e.u,
      target: e.v,
      cost: e.cost,
    }));

    if (simulationRef.current === null) {
      simulationRef.current = d3
        .forceSimulation<NodeDatum, LinkDatum>(nodes)
        .force(
          "link",
          d3
            .forceLink<NodeDatum, LinkDatum>(links)
            .id((n) => n.id)
            .distance(FORCE_LINK_DISTANCE)
            .strength(0.4),
        )
        .force("charge", d3.forceManyBody<NodeDatum>().strength(FORCE_CHARGE))
        .force("center", d3.forceCenter(WIDTH / 2, HEIGHT / 2))
        .force("collide", d3.forceCollide<NodeDatum>().radius(14))
        .alpha(0.9)
        .alphaDecay(0.03);
    } else {
      simulationRef.current.nodes(nodes);
      const linkForce = simulationRef.current.force("link") as d3.ForceLink<NodeDatum, LinkDatum>;
      linkForce.links(links);
      simulationRef.current.alpha(0.5).restart();
    }
  }, [topology]);

  // Per-node agent occupancy from the live tick frame.
  const occupancy = useMemo(() => {
    const counts = new Map<number, number>();
    if (lastFrame !== null) {
      for (const pos of Object.values(lastFrame.agent_positions)) {
        counts.set(pos, (counts.get(pos) ?? 0) + 1);
      }
    }
    return counts;
  }, [lastFrame]);

  // Pick a representative agent id per node so a click on the node
  // tile selects the lowest-id agent currently there. Arena2D shows
  // node occupancy rather than individual agent dots, so this is the
  // best handoff we can offer until a per-agent overlay lands.
  const firstAgentByNode = useMemo(() => {
    const m = new Map<number, number>();
    if (lastFrame === null) return m;
    for (const [idStr, pos] of Object.entries(lastFrame.agent_positions)) {
      const aid = Number(idStr);
      const cur = m.get(pos);
      if (cur === undefined || aid < cur) m.set(pos, aid);
    }
    return m;
  }, [lastFrame]);

  // d3 redraw loop, driven by simulation ticks.
  useEffect(() => {
    const simulation = simulationRef.current;
    const svg = svgRef.current;
    if (simulation === null || svg === null) return;

    const handler = () => {
      const linkElems = svg.querySelectorAll<SVGLineElement>("[data-link]");
      const nodeElems = svg.querySelectorAll<SVGGElement>("[data-node]");
      let i = 0;
      simulation.force("link");
      const links = (simulation.force("link") as d3.ForceLink<NodeDatum, LinkDatum>).links();
      for (const link of links) {
        const elem = linkElems[i++];
        if (elem === undefined) continue;
        const src = link.source as NodeDatum;
        const dst = link.target as NodeDatum;
        elem.setAttribute("x1", String(src.x ?? 0));
        elem.setAttribute("y1", String(src.y ?? 0));
        elem.setAttribute("x2", String(dst.x ?? 0));
        elem.setAttribute("y2", String(dst.y ?? 0));
      }
      let j = 0;
      for (const n of simulation.nodes()) {
        const elem = nodeElems[j++];
        if (elem === undefined) continue;
        elem.setAttribute("transform", `translate(${n.x ?? 0},${n.y ?? 0})`);
      }
    };
    simulation.on("tick", handler);
    return () => {
      simulation.on("tick", null);
    };
  });

  if (topology === null) {
    return (
      <div className="flex h-full w-full items-center justify-center text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
        arena topology loading
        <span className="animate-pulse">…</span>
      </div>
    );
  }

  // Compute edge color scale (cyan = cheap, ember = expensive).
  const costs = topology.edges.map((e) => e.cost);
  const costMin = Math.min(...costs);
  const costMax = Math.max(...costs);
  const colorScale = d3
    .scaleLinear<string>()
    .domain([costMin, costMax])
    .range([
      "color-mix(in srgb, var(--color-penumbra-cyan) 80%, transparent)",
      "color-mix(in srgb, var(--color-penumbra-ember) 70%, transparent)",
    ])
    .clamp(true);

  const links = topology.edges;
  const nodes = Array.from(nodeMapRef.current.values());

  const onNodeClick = (nodeId: number) => {
    const aid = firstAgentByNode.get(nodeId);
    if (aid !== undefined) setSelectedAgentId(aid);
  };

  const setNodeTooltip = (e: React.MouseEvent, n: NodeDatum) => {
    const count = occupancy.get(n.id) ?? 0;
    setTooltip({ kind: "node", id: n.id, count, x: e.clientX, y: e.clientY });
  };
  const setEdgeTooltip = (e: React.MouseEvent, l: { u: number; v: number; cost: number }) => {
    setTooltip({ kind: "edge", u: l.u, v: l.v, cost: l.cost, x: e.clientX, y: e.clientY });
  };

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: presentational wrapper hosts only a hover-cancel handler
    <div className="relative h-full w-full" onMouseLeave={() => setTooltip(null)}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-full w-full"
        role="img"
        aria-label="Penumbra arena graph"
      >
        <g data-edges>
          {links.map((l) => (
            // biome-ignore lint/a11y/noStaticElementInteractions: SVG <line> is a tooltip hover target only (no click)
            <line
              key={`${l.u}-${l.v}`}
              data-link
              stroke={colorScale(l.cost)}
              strokeWidth={1}
              strokeOpacity={0.7}
              onMouseEnter={(e) => setEdgeTooltip(e, l)}
              onMouseMove={(e) => setEdgeTooltip(e, l)}
              onMouseLeave={() => setTooltip(null)}
              style={{ cursor: "default" }}
            />
          ))}
        </g>
        <g data-nodes>
          {nodes.map((n) => {
            const count = occupancy.get(n.id) ?? 0;
            const baseRadius = 5;
            const radius = baseRadius + Math.sqrt(count) * 2.5;
            const clickable = count > 0;
            return (
              // biome-ignore lint/a11y/noStaticElementInteractions: SVG <g> tile hit target; role="button" only when clickable
              <g
                key={n.id}
                data-node
                role={clickable ? "button" : undefined}
                tabIndex={clickable ? 0 : undefined}
                aria-label={clickable ? `Inspect agents at tile ${n.id}` : undefined}
                onClick={() => onNodeClick(n.id)}
                onKeyDown={(e) => {
                  if (clickable && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    onNodeClick(n.id);
                  }
                }}
                onMouseEnter={(e) => setNodeTooltip(e, n)}
                onMouseMove={(e) => setNodeTooltip(e, n)}
                onMouseLeave={() => setTooltip(null)}
                style={{ cursor: clickable ? "pointer" : "default" }}
              >
                {n.isGoal && (
                  <circle
                    r={radius + 6}
                    fill="none"
                    stroke="var(--color-penumbra-cyan)"
                    strokeWidth={1.2}
                    strokeDasharray="3 3"
                    opacity={0.8}
                  />
                )}
                <circle
                  r={radius}
                  fill={
                    n.isGoal
                      ? "var(--color-penumbra-cyan-bg)"
                      : count > 0
                        ? "var(--color-penumbra-panel)"
                        : "var(--color-penumbra-bg)"
                  }
                  stroke={count > 0 ? "var(--color-penumbra-text)" : "var(--color-penumbra-border)"}
                  strokeWidth={count > 0 ? 1.2 : 0.7}
                />
                {count > 0 && (
                  <text
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={10}
                    fill="var(--color-penumbra-text)"
                    style={{ fontFamily: "var(--font-mono)", pointerEvents: "none" }}
                  >
                    {count}
                  </text>
                )}
                {n.isGoal && (
                  <text
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={8}
                    y={radius + 12}
                    fill="var(--color-penumbra-cyan)"
                    style={{ fontFamily: "var(--font-mono)", pointerEvents: "none" }}
                  >
                    goal {n.id}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>
      {tooltip !== null && <ArenaTooltip tooltip={tooltip} />}
    </div>
  );
}

function ArenaTooltip({ tooltip }: { tooltip: Tooltip }) {
  const label =
    tooltip.kind === "node"
      ? `tile #${tooltip.id} · agents: ${tooltip.count}`
      : `edge ${tooltip.u}↔${tooltip.v} · weight ${tooltip.cost.toFixed(2)}`;
  return (
    <div
      role="tooltip"
      className="pointer-events-none fixed z-50 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] px-2 py-1 font-mono text-[10px] text-[color:var(--color-penumbra-text)] shadow-lg"
      style={{ left: tooltip.x + 12, top: tooltip.y + 12 }}
    >
      {label}
    </div>
  );
}
