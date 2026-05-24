/**
 * World view v2 — città, strade, personaggi animati.
 *
 * Design rifinito sopra la versione "graph teorico":
 * - Sfondo a pattern (grain dot) per dare densità di territorio.
 * - Nodi disegnati come "città": tile arrotondato + glow per i goal,
 *   tile più piccolo per gli outpost, etichetta `#id`.
 * - Strade: stroke spesso 2 px con linecap arrotondato; colorazione
 *   cyan↔ember sulla scala del costo OU. Stroke più opaco per le
 *   strade economiche (più "battute"), più trasparente per quelle
 *   costose. Un drop-shadow leggero le stacca dal fondo.
 * - Agenti: triangoli direzionati che puntano verso la destinazione
 *   in corso (rotazione interpolata dal vettore prev→current).
 *   Animazione smooth lungo l'arco via transizione CSS.
 * - Trail: la posizione precedente lascia un'ombra leggera che svanisce.
 */

import * as d3 from "d3";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSelectedAgentStore } from "../stores/selectedAgent";
import { useEffectiveFrame } from "../streams/effectiveFrame";
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

const WIDTH = 980;
const HEIGHT = 580;
const FORCE_LINK_DISTANCE = 78;
const FORCE_CHARGE = -240;
const NODE_RADIUS_OUTPOST = 7;
const NODE_RADIUS_GOAL = 11;
const GOAL_HALO_RADIUS = 20;
const AGENT_SIZE = 6;
const AGENT_ORBIT_RADIUS = 11;

/** Stable hue per agent id; golden-ratio spread for colourblind separation. */
function agentColor(id: number): string {
  const hue = ((id * 0.6180339887) % 1) * 360;
  return `oklch(0.78 0.18 ${hue.toFixed(1)})`;
}

/** Position N agents on a small ring around a node centre. */
function orbitPosition(index: number, total: number, cx: number, cy: number): NodePosition {
  if (total === 1) return { x: cx, y: cy };
  const angle = (index / total) * Math.PI * 2 - Math.PI / 2;
  return {
    x: cx + AGENT_ORBIT_RADIUS * Math.cos(angle),
    y: cy + AGENT_ORBIT_RADIUS * Math.sin(angle),
  };
}

interface AgentRender {
  id: number;
  x: number;
  y: number;
  nodeId: number;
  prevX: number | null;
  prevY: number | null;
}

export function WorldView() {
  const topology = useArenaTopology();
  const lastFrame = useEffectiveFrame();
  const setSelectedAgentId = useSelectedAgentStore((s) => s.setSelectedAgentId);
  const [positions, setPositions] = useState<Map<number, NodePosition>>(new Map());
  const previousAgentRef = useRef<Map<number, AgentRender>>(new Map());

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
          .strength(0.55),
      )
      .force("charge", d3.forceManyBody<NodeDatum>().strength(FORCE_CHARGE))
      .force("center", d3.forceCenter(WIDTH / 2, HEIGHT / 2))
      .force("collide", d3.forceCollide<NodeDatum>().radius(NODE_RADIUS_GOAL + 14))
      .stop();

    for (let i = 0; i < 400; i++) sim.tick();

    const newPositions = new Map<number, NodePosition>();
    for (const n of sim.nodes()) {
      newPositions.set(n.id, { x: n.x ?? WIDTH / 2, y: n.y ?? HEIGHT / 2 });
    }
    setPositions(newPositions);
  }, [topology]);

  // Compute per-agent rendering positions from the live frame, tracking previous.
  const agentRenders = useMemo<AgentRender[]>(() => {
    if (lastFrame === null) return [];
    // Group agents by node, then orbit them around the node.
    const byNode = new Map<number, number[]>();
    for (const [idStr, nodeId] of Object.entries(lastFrame.agent_positions)) {
      const aid = Number(idStr);
      const arr = byNode.get(nodeId) ?? [];
      arr.push(aid);
      byNode.set(nodeId, arr);
    }
    const out: AgentRender[] = [];
    for (const [nodeId, agentIds] of byNode.entries()) {
      const np = positions.get(nodeId);
      if (np === undefined) continue;
      const sorted = [...agentIds].sort((a, b) => a - b);
      for (let i = 0; i < sorted.length; i++) {
        const aid = sorted[i] as number;
        const p = orbitPosition(i, sorted.length, np.x, np.y);
        const prev = previousAgentRef.current.get(aid);
        out.push({
          id: aid,
          x: p.x,
          y: p.y,
          nodeId,
          prevX: prev?.x ?? null,
          prevY: prev?.y ?? null,
        });
      }
    }
    // Snapshot current for next frame's prev.
    const newMap = new Map<number, AgentRender>();
    for (const a of out) newMap.set(a.id, a);
    previousAgentRef.current = newMap;
    return out;
  }, [lastFrame, positions]);

  // Cost color scale.
  const colorScale = useMemo(() => {
    if (topology === null) return null;
    const costs = topology.edges.map((e) => e.cost);
    return d3
      .scaleLinear<string>()
      .domain([Math.min(...costs), Math.max(...costs)])
      .range([
        "color-mix(in srgb, var(--color-penumbra-cyan) 75%, transparent)",
        "color-mix(in srgb, var(--color-penumbra-ember) 70%, transparent)",
      ])
      .clamp(true);
  }, [topology]);

  // Edge thickness scale: cheap = thicker (well-trodden road).
  const widthScale = useMemo(() => {
    if (topology === null) return null;
    const costs = topology.edges.map((e) => e.cost);
    return d3
      .scaleLinear<number>()
      .domain([Math.min(...costs), Math.max(...costs)])
      .range([2.6, 1.2])
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
      <defs>
        {/* Subtle dot-grid background — gives the world a "map paper" feel. */}
        <pattern id="penumbra-world-grain" width={18} height={18} patternUnits="userSpaceOnUse">
          <circle
            cx={9}
            cy={9}
            r={0.7}
            fill="color-mix(in srgb, var(--color-penumbra-border) 70%, transparent)"
          />
        </pattern>
        <filter id="penumbra-goal-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3.5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="penumbra-agent-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="1.2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="penumbra-road-shadow" x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur stdDeviation="0.6" />
        </filter>
      </defs>

      <rect width={WIDTH} height={HEIGHT} fill="url(#penumbra-world-grain)" />

      {/* Roads (drawn first so they sit under everything). */}
      <g data-edges>
        {topology.edges.map((e) => {
          const a = positions.get(e.u);
          const b = positions.get(e.v);
          if (a === undefined || b === undefined || colorScale === null || widthScale === null)
            return null;
          return (
            <line
              key={`${e.u}-${e.v}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={colorScale(e.cost)}
              strokeWidth={widthScale(e.cost)}
              strokeLinecap="round"
              strokeOpacity={0.92}
            />
          );
        })}
      </g>

      {/* Cities + outposts. */}
      <g data-nodes>
        {topology.nodes.map((nodeId) => {
          const p = positions.get(nodeId);
          if (p === undefined) return null;
          const isGoal = goalSet.has(nodeId);
          if (isGoal) {
            return (
              <g
                key={nodeId}
                transform={`translate(${p.x},${p.y})`}
                filter="url(#penumbra-goal-glow)"
              >
                {/* outer halo */}
                <circle
                  r={GOAL_HALO_RADIUS}
                  fill="color-mix(in srgb, var(--color-penumbra-cyan) 14%, transparent)"
                />
                {/* dashed ring */}
                <circle
                  r={NODE_RADIUS_GOAL + 4}
                  fill="none"
                  stroke="var(--color-penumbra-cyan)"
                  strokeWidth={1.2}
                  strokeDasharray="3 3"
                  opacity={0.9}
                />
                {/* core (rounded square) */}
                <rect
                  x={-NODE_RADIUS_GOAL}
                  y={-NODE_RADIUS_GOAL}
                  width={NODE_RADIUS_GOAL * 2}
                  height={NODE_RADIUS_GOAL * 2}
                  rx={3}
                  fill="var(--color-penumbra-cyan-bg)"
                  stroke="var(--color-penumbra-cyan)"
                  strokeWidth={1.4}
                />
                {/* star glyph */}
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={11}
                  fill="var(--color-penumbra-cyan)"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  ★
                </text>
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={8.5}
                  y={GOAL_HALO_RADIUS + 6}
                  fill="var(--color-penumbra-cyan)"
                  style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}
                >
                  goal {nodeId}
                </text>
              </g>
            );
          }
          // Outpost — small rounded tile + node id under it.
          return (
            <g key={nodeId} transform={`translate(${p.x},${p.y})`}>
              <rect
                x={-NODE_RADIUS_OUTPOST}
                y={-NODE_RADIUS_OUTPOST}
                width={NODE_RADIUS_OUTPOST * 2}
                height={NODE_RADIUS_OUTPOST * 2}
                rx={1.8}
                fill="var(--color-penumbra-panel)"
                stroke="var(--color-penumbra-border)"
                strokeWidth={0.9}
              />
              <text
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={6.5}
                fill="var(--color-penumbra-muted)"
                style={{ fontFamily: "var(--font-mono)" }}
                y={NODE_RADIUS_OUTPOST + 8}
              >
                #{nodeId}
              </text>
            </g>
          );
        })}
      </g>

      {/* Agents — directional triangles, animated. */}
      <g data-agents filter="url(#penumbra-agent-glow)">
        {agentRenders.map(({ id, x, y, prevX, prevY }) => {
          // Compute heading angle from prev→current; default to north if no prev.
          let angleDeg = -90;
          if (prevX !== null && prevY !== null) {
            const dx = x - prevX;
            const dy = y - prevY;
            const dist = Math.hypot(dx, dy);
            if (dist > 0.5) {
              angleDeg = (Math.atan2(dy, dx) * 180) / Math.PI;
            }
          }
          const color = agentColor(id);
          return (
            // biome-ignore lint/a11y/useSemanticElements: cannot nest a <button> inside <svg>; SVG hit target uses role
            <g
              key={id}
              role="button"
              tabIndex={0}
              aria-label={`Inspect agent ${id}`}
              onClick={() => setSelectedAgentId(id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setSelectedAgentId(id);
                }
              }}
              style={{
                transform: `translate(${x}px, ${y}px) rotate(${angleDeg}deg)`,
                transition: "transform 320ms cubic-bezier(0.4, 0.0, 0.2, 1)",
                transformBox: "fill-box",
                transformOrigin: "center",
                cursor: "pointer",
              }}
            >
              {/* Trail/afterimage — small soft dot at the back of the triangle */}
              <circle cx={-AGENT_SIZE - 1} cy={0} r={1.2} fill={color} opacity={0.5} />
              {/* Triangle: tip at +X (rotates so tip points toward heading). */}
              <polygon
                points={`${AGENT_SIZE},0 ${-AGENT_SIZE * 0.6},${-AGENT_SIZE * 0.6} ${-AGENT_SIZE * 0.6},${AGENT_SIZE * 0.6}`}
                fill={color}
                stroke="var(--color-penumbra-bg)"
                strokeWidth={0.6}
              />
              <title>agent {id}</title>
            </g>
          );
        })}
      </g>
    </svg>
  );
}
