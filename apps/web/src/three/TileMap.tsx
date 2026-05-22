/**
 * Dwarf-Fortress-style tile-map of the Penumbra world (v2).
 *
 * v1 had two readability problems:
 * 1. Roads filled entire tile cells with '#' glyphs, so 95 edges
 *    crisscrossed and the map became a wall of road. Now roads are
 *    THIN LINES between city pixel-centres; the underlying terrain
 *    glyphs stay legible.
 * 2. With 50 agents collapsed to 2 nodes, the stack offset (±3px)
 *    overlapped everyone into a single colored blob. Now agents
 *    orbit their city in expanding rings (8 per ring), so even all
 *    50 at one node fan out around it.
 *
 * It also adds traversal HEAT:
 * - Every edge has a `heat` value in [0, 1].
 * - When an agent crosses an edge, we set heat[edge] = 1.0.
 * - Each animation frame, heat decays by ~0.5% (≈3 s half-life).
 * - Roads with high heat render bright + thick; idle roads fade.
 * - So the map reads as a living network: you SEE which paths the
 *   swarm is currently using vs which sit unused.
 *
 * Layers (back to front)
 * - Terrain (procedural biomes from simplex-noise) — rasterised
 *   once to an offscreen canvas, blitted per frame.
 * - Roads — drawn per frame on the live canvas as thin lines,
 *   stroke based on heat.
 * - Cities + goals — drawn per frame on top of roads.
 * - Agents — '@' glyphs at orbit positions, drawn per frame.
 */

import { useEffect, useMemo, useRef } from "react";
import { createNoise2D } from "simplex-noise";
import { usePenumbraStore } from "../streams/store";
import { useArenaTopology } from "../streams/topology";

const COLS = 90;
const ROWS = 54;
const CELL = 12;
const WIDTH = COLS * CELL;
const HEIGHT = ROWS * CELL;
const FONT = `${CELL - 1}px "JetBrains Mono", "Fira Code", monospace`;
const FONT_AGENT = `bold ${CELL + 6}px "JetBrains Mono", "Fira Code", monospace`;
const FONT_CITY = `${CELL + 2}px "JetBrains Mono", "Fira Code", monospace`;

const AGENT_TILE_PER_SEC = 6;

// Edge-heat decay: heat *= HEAT_DECAY_PER_FRAME ⇒ half-life ≈ 3 s at 60 fps.
const HEAT_DECAY_PER_FRAME = 0.996;
const HEAT_MIN_VISIBLE = 0.04;

// Agent ring spacing when many agents stack at one node.
// Ring r holds AGENTS_PER_RING agents at radius
//   RING_INNER + r * RING_STEP. Ring 0 has a non-zero radius so the
// first 8 agents fan out instead of collapsing onto the city centre.
const AGENT_RING_INNER = 11;
const AGENT_RING_STEP = 9;
const AGENTS_PER_RING = 8;

type Biome = "water" | "mountain" | "forest" | "grass" | "scrub";

const BIOME_GLYPH: Record<Biome, string> = {
  water: "~",
  mountain: "^",
  forest: "T",
  grass: ".",
  scrub: ",",
};

const BIOME_FG: Record<Biome, string> = {
  water: "#2c5566",
  mountain: "#54585f",
  forest: "#3a6b3a",
  grass: "#3f5839",
  scrub: "#5d6042",
};

const BIOME_BG: Record<Biome, string> = {
  water: "#162935",
  mountain: "#1d2026",
  forest: "#15221a",
  grass: "#171c14",
  scrub: "#1d1f15",
};

const ROAD_IDLE = "#3b3621";
const ROAD_HOT = "#d4a44a";
const CITY_FG = "#e2e5ea";
const CITY_BG = "#2d2f39";
const GOAL_FG = "#86dfe6";
const GOAL_BG = "#0e2e33";
const GOAL_HALO = "rgba(134, 223, 230, 0.18)";

interface TileLayout {
  biome: Biome[][];
  /** Map nodeId -> (col, row) tile centre. */
  nodeCells: Map<number, [number, number]>;
  /** Topology edges with stable canonical key u<v. */
  edges: { key: string; u: number; v: number }[];
  /** For each edge key, the Bresenham path (col,row tiles). */
  edgePaths: Map<string, [number, number][]>;
}

function edgeKey(u: number, v: number): string {
  return u < v ? `${u}-${v}` : `${v}-${u}`;
}

function agentColor(id: number): string {
  const hue = ((id * 0.6180339887) % 1) * 360;
  return `oklch(0.82 0.18 ${hue.toFixed(1)})`;
}

function seededRng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 0xffffffff;
  };
}

function classifyBiome(elevation: number, moisture: number): Biome {
  if (elevation < 0.32) return "water";
  if (elevation > 0.74) return "mountain";
  if (elevation < 0.42 || elevation > 0.65) return "scrub";
  if (moisture > 0.55) return "forest";
  return "grass";
}

function bresenham(x0: number, y0: number, x1: number, y1: number): [number, number][] {
  const out: [number, number][] = [];
  let x = x0;
  let y = y0;
  const dx = Math.abs(x1 - x0);
  const dy = Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1;
  const sy = y0 < y1 ? 1 : -1;
  let err = dx - dy;
  for (;;) {
    out.push([x, y]);
    if (x === x1 && y === y1) break;
    const e2 = err * 2;
    if (e2 > -dy) {
      err -= dy;
      x += sx;
    }
    if (e2 < dx) {
      err += dx;
      y += sy;
    }
  }
  return out;
}

// Traversal cost per biome. Water + mountain are expensive so A*
// routes roads AROUND them; grass + forest are cheap so the path
// flows through habitable terrain. Tuning these reshapes the world.
const BIOME_COST: Record<Biome, number> = {
  water: 14,
  mountain: 12,
  scrub: 2.2,
  forest: 1.6,
  grass: 1,
};

/**
 * Min-heap priority queue keyed by f-score. Custom rather than a
 * library so we don't ship another dep. Stores [priority, value]
 * tuples; sift up/down by integer index. Performance: enough for
 * one A* run over a 90×54 grid in a few ms.
 */
class MinHeap<T> {
  private data: [number, T][] = [];
  get size(): number {
    return this.data.length;
  }
  push(prio: number, value: T): void {
    this.data.push([prio, value]);
    this.siftUp(this.data.length - 1);
  }
  pop(): T | undefined {
    if (this.data.length === 0) return undefined;
    const top = this.data[0];
    const last = this.data.pop();
    if (this.data.length > 0 && last !== undefined) {
      this.data[0] = last;
      this.siftDown(0);
    }
    return top ? top[1] : undefined;
  }
  private siftUp(i: number): void {
    while (i > 0) {
      const parent = (i - 1) >> 1;
      const cur = this.data[i];
      const par = this.data[parent];
      if (cur === undefined || par === undefined || cur[0] >= par[0]) break;
      this.data[i] = par;
      this.data[parent] = cur;
      i = parent;
    }
  }
  private siftDown(i: number): void {
    const n = this.data.length;
    for (;;) {
      const l = 2 * i + 1;
      const r = l + 1;
      let smallest = i;
      const small = this.data[smallest];
      const left = l < n ? this.data[l] : undefined;
      const right = r < n ? this.data[r] : undefined;
      if (small === undefined) return;
      if (left !== undefined && left[0] < small[0]) smallest = l;
      if (right !== undefined && right[0] < (this.data[smallest] as [number, T])[0]) smallest = r;
      if (smallest === i) break;
      const a = this.data[i];
      const b = this.data[smallest];
      if (a === undefined || b === undefined) return;
      this.data[i] = b;
      this.data[smallest] = a;
      i = smallest;
    }
  }
}

/**
 * 4-connected A* on the biome grid, minimising sum of BIOME_COST.
 * Returns the ordered list of (col, row) tiles from start to goal
 * (inclusive on both ends).
 */
function astar(
  biome: Biome[][],
  start: [number, number],
  goal: [number, number],
): [number, number][] {
  const [sx, sy] = start;
  const [gx, gy] = goal;
  const idx = (x: number, y: number) => y * COLS + x;
  const total = COLS * ROWS;
  const gScore = new Float64Array(total).fill(Infinity);
  const came = new Int32Array(total).fill(-1);
  const closed = new Uint8Array(total);
  gScore[idx(sx, sy)] = 0;
  const heap = new MinHeap<number>();
  heap.push(0, idx(sx, sy));
  const goalIdx = idx(gx, gy);

  // Manhattan distance as the heuristic — admissible on a 4-connected grid.
  const heur = (x: number, y: number) => Math.abs(x - gx) + Math.abs(y - gy);

  while (heap.size > 0) {
    const cur = heap.pop();
    if (cur === undefined) break;
    if (cur === goalIdx) {
      // Reconstruct.
      const out: [number, number][] = [];
      let c: number = cur;
      while (c !== -1) {
        const y = Math.floor(c / COLS);
        const x = c - y * COLS;
        out.push([x, y]);
        c = came[c] ?? -1;
      }
      out.reverse();
      return out;
    }
    if (closed[cur]) continue;
    closed[cur] = 1;
    const cy = Math.floor(cur / COLS);
    const cx = cur - cy * COLS;
    const neighbours: [number, number][] = [
      [cx + 1, cy],
      [cx - 1, cy],
      [cx, cy + 1],
      [cx, cy - 1],
    ];
    for (const [nx, ny] of neighbours) {
      if (nx < 0 || ny < 0 || nx >= COLS || ny >= ROWS) continue;
      const nIdx = idx(nx, ny);
      if (closed[nIdx]) continue;
      const row = biome[ny];
      if (row === undefined) continue;
      const tileBiome = row[nx];
      if (tileBiome === undefined) continue;
      const step = BIOME_COST[tileBiome];
      const tentative = (gScore[cur] ?? Infinity) + step;
      if (tentative < (gScore[nIdx] ?? Infinity)) {
        came[nIdx] = cur;
        gScore[nIdx] = tentative;
        heap.push(tentative + heur(nx, ny), nIdx);
      }
    }
  }
  // No path (shouldn't happen on a connected grid). Fall back to Bresenham.
  return bresenham(sx, sy, gx, gy);
}

function layoutNodes(
  nodes: number[],
  edges: { u: number; v: number }[],
  rng: () => number,
): Map<number, [number, number]> {
  const pos = new Map<number, { x: number; y: number }>();
  const cx = COLS / 2;
  const cy = ROWS / 2;
  const radius = Math.min(COLS, ROWS) * 0.35;
  nodes.forEach((nodeId, i) => {
    const angle = (i / nodes.length) * Math.PI * 2 + rng() * 0.3;
    pos.set(nodeId, {
      x: cx + radius * Math.cos(angle) + (rng() - 0.5) * 2,
      y: cy + radius * Math.sin(angle) + (rng() - 0.5) * 2,
    });
  });
  const linkDist = Math.min(COLS, ROWS) * 0.14;
  for (let iter = 0; iter < 250; iter++) {
    const forces = new Map<number, { fx: number; fy: number }>();
    for (const id of nodes) forces.set(id, { fx: 0, fy: 0 });
    for (let i = 0; i < nodes.length; i++) {
      const idA = nodes[i] as number;
      const a = pos.get(idA);
      if (a === undefined) continue;
      for (let j = i + 1; j < nodes.length; j++) {
        const idB = nodes[j] as number;
        const b = pos.get(idB);
        if (b === undefined) continue;
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const d2 = dx * dx + dy * dy + 0.01;
        const force = 28 / d2;
        const fx = force * dx;
        const fy = force * dy;
        const fa = forces.get(idA);
        const fb = forces.get(idB);
        if (fa) {
          fa.fx += fx;
          fa.fy += fy;
        }
        if (fb) {
          fb.fx -= fx;
          fb.fy -= fy;
        }
      }
    }
    for (const e of edges) {
      const a = pos.get(e.u);
      const b = pos.get(e.v);
      const fa = forces.get(e.u);
      const fb = forces.get(e.v);
      if (a === undefined || b === undefined || fa === undefined || fb === undefined) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) + 0.01;
      const k = (dist - linkDist) * 0.04;
      fa.fx += (dx / dist) * k;
      fa.fy += (dy / dist) * k;
      fb.fx -= (dx / dist) * k;
      fb.fy -= (dy / dist) * k;
    }
    for (const id of nodes) {
      const p = pos.get(id);
      const f = forces.get(id);
      if (p === undefined || f === undefined) continue;
      p.x += f.fx + (cx - p.x) * 0.01;
      p.y += f.fy + (cy - p.y) * 0.01;
      p.x = Math.max(3, Math.min(COLS - 4, p.x));
      p.y = Math.max(3, Math.min(ROWS - 4, p.y));
    }
  }
  const snapped = new Map<number, [number, number]>();
  const taken = new Set<string>();
  for (const id of nodes) {
    const p = pos.get(id);
    if (p === undefined) continue;
    let col = Math.round(p.x);
    let row = Math.round(p.y);
    let attempt = 0;
    while (taken.has(`${col},${row}`) && attempt < 50) {
      attempt++;
      const r = Math.ceil(Math.sqrt(attempt));
      const offsets = [
        [r, 0],
        [-r, 0],
        [0, r],
        [0, -r],
        [r, r],
        [-r, -r],
        [r, -r],
        [-r, r],
      ];
      const offset = offsets[attempt % offsets.length] as [number, number];
      col = Math.round(p.x) + offset[0];
      row = Math.round(p.y) + offset[1];
    }
    col = Math.max(2, Math.min(COLS - 3, col));
    row = Math.max(2, Math.min(ROWS - 3, row));
    taken.add(`${col},${row}`);
    snapped.set(id, [col, row]);
  }
  return snapped;
}

function buildTileLayout(
  nodes: number[],
  edges: { u: number; v: number }[],
  seed = 42,
): TileLayout {
  const rng = seededRng(seed);
  const elevationNoise = createNoise2D(rng);
  const moistureNoise = createNoise2D(rng);
  const sampleElev = (c: number, r: number) => {
    const a = (elevationNoise(c * 0.07, r * 0.07) + 1) / 2;
    const b = (elevationNoise(c * 0.18, r * 0.18) + 1) / 2;
    return a * 0.65 + b * 0.35;
  };
  const sampleMoisture = (c: number, r: number) => {
    const a = (moistureNoise(c * 0.05, r * 0.05) + 1) / 2;
    const b = (moistureNoise(c * 0.13, r * 0.13) + 1) / 2;
    return a * 0.6 + b * 0.4;
  };

  const biome: Biome[][] = [];
  for (let r = 0; r < ROWS; r++) {
    const row: Biome[] = [];
    for (let c = 0; c < COLS; c++) {
      row.push(classifyBiome(sampleElev(c, r), sampleMoisture(c, r)));
    }
    biome.push(row);
  }

  const nodeCells = layoutNodes(nodes, edges, rng);
  const canonEdges = edges.map((e) => ({ key: edgeKey(e.u, e.v), u: e.u, v: e.v }));

  // A* on the biome grid for every edge. Roads now bend around water
  // and mountains instead of slicing through them in straight lines.
  // ~95 edges × ~500 tiles per path ≈ 50k iterations total, runs in
  // a few ms on the client.
  const edgePaths = new Map<string, [number, number][]>();
  for (const e of canonEdges) {
    const a = nodeCells.get(e.u);
    const b = nodeCells.get(e.v);
    if (a === undefined || b === undefined) continue;
    edgePaths.set(e.key, astar(biome, a, b));
  }

  return { biome, nodeCells, edges: canonEdges, edgePaths };
}

/** Paint the terrain layer (biomes only — no roads, no cities). */
function paintTerrain(ctx: CanvasRenderingContext2D, layout: TileLayout): void {
  ctx.clearRect(0, 0, WIDTH, HEIGHT);
  ctx.textBaseline = "middle";
  ctx.textAlign = "center";
  ctx.font = FONT;
  for (let r = 0; r < ROWS; r++) {
    const biomeRow = layout.biome[r];
    if (biomeRow === undefined) continue;
    for (let c = 0; c < COLS; c++) {
      const tileBiome = biomeRow[c];
      if (tileBiome === undefined) continue;
      ctx.fillStyle = BIOME_BG[tileBiome];
      ctx.fillRect(c * CELL, r * CELL, CELL, CELL);
      ctx.fillStyle = BIOME_FG[tileBiome];
      ctx.fillText(BIOME_GLYPH[tileBiome], c * CELL + CELL / 2, r * CELL + CELL / 2 + 0.5);
    }
  }
}

/** Linearly interpolate between two hex colors (no alpha). */
function lerpColor(a: string, b: string, t: number): string {
  const parse = (s: string) => [
    parseInt(s.slice(1, 3), 16),
    parseInt(s.slice(3, 5), 16),
    parseInt(s.slice(5, 7), 16),
  ];
  const [ar, ag, ab] = parse(a) as [number, number, number];
  const [br, bg, bb] = parse(b) as [number, number, number];
  const r = Math.round(ar + (br - ar) * t);
  const g = Math.round(ag + (bg - ag) * t);
  const bl = Math.round(ab + (bb - ab) * t);
  return `rgb(${r}, ${g}, ${bl})`;
}

interface AgentAnim {
  /** path of tile centres in canvas px. */
  pathPx: [number, number][];
  startedAt: number;
  durationMs: number;
}

export function TileMap() {
  const topology = useArenaTopology();
  const lastFrame = usePenumbraStore((s) => s.lastFrame);
  const terrainCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const liveCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const animsRef = useRef<Map<number, AgentAnim>>(new Map());
  const previousNodesRef = useRef<Map<number, number>>(new Map());
  const edgeHeatRef = useRef<Map<string, number>>(new Map());

  const layout = useMemo(() => {
    if (topology === null) return null;
    return buildTileLayout(topology.nodes, topology.edges);
  }, [topology]);

  // Paint terrain once when layout arrives.
  useEffect(() => {
    if (layout === null || terrainCanvasRef.current === null) return;
    const canvas = terrainCanvasRef.current;
    canvas.width = WIDTH;
    canvas.height = HEIGHT;
    const ctx = canvas.getContext("2d");
    if (ctx === null) return;
    paintTerrain(ctx, layout);
  }, [layout]);

  // Whenever the live frame changes, queue or update agent walk animations + bump edge heat.
  useEffect(() => {
    if (lastFrame === null || layout === null) return;
    const now = performance.now();
    for (const [idStr, nodeId] of Object.entries(lastFrame.agent_positions)) {
      const aid = Number(idStr);
      const prevNode = previousNodesRef.current.get(aid);
      if (prevNode === nodeId) continue;
      if (prevNode === undefined) {
        previousNodesRef.current.set(aid, nodeId);
        continue;
      }
      const key = edgeKey(prevNode, nodeId);
      edgeHeatRef.current.set(key, 1.0);

      const a = layout.nodeCells.get(prevNode);
      const b = layout.nodeCells.get(nodeId);
      if (a === undefined || b === undefined) {
        previousNodesRef.current.set(aid, nodeId);
        continue;
      }
      const stored = layout.edgePaths.get(key);
      const tilePath =
        stored !== undefined && stored.length >= 2 ? stored : bresenham(a[0], a[1], b[0], b[1]);
      // Convert to canvas pixel centres, oriented prev → current.
      let oriented: [number, number][];
      const first = tilePath[0];
      if (first !== undefined && first[0] === a[0] && first[1] === a[1]) {
        oriented = tilePath;
      } else {
        oriented = [...tilePath].reverse();
      }
      const pathPx = oriented.map(
        ([c, r]) => [c * CELL + CELL / 2, r * CELL + CELL / 2] as [number, number],
      );
      const durationMs = (pathPx.length / AGENT_TILE_PER_SEC) * 1000;
      animsRef.current.set(aid, { pathPx, startedAt: now, durationMs });
      previousNodesRef.current.set(aid, nodeId);
    }
  }, [lastFrame, layout]);

  // Animation frame loop: terrain → roads (heat) → cities → agents.
  useEffect(() => {
    if (layout === null) return;
    let raf = 0;
    const tick = () => {
      const live = liveCanvasRef.current;
      const terrain = terrainCanvasRef.current;
      if (live === null || terrain === null) {
        raf = requestAnimationFrame(tick);
        return;
      }
      if (live.width !== WIDTH) live.width = WIDTH;
      if (live.height !== HEIGHT) live.height = HEIGHT;
      const ctx = live.getContext("2d");
      if (ctx === null) {
        raf = requestAnimationFrame(tick);
        return;
      }
      ctx.clearRect(0, 0, WIDTH, HEIGHT);
      ctx.drawImage(terrain, 0, 0);

      // Roads — A*-routed polylines, stroke based on traversal heat.
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      // First draw the IDLE network as a thin baseline so the topology
      // is always at least faintly readable even with zero traffic.
      ctx.strokeStyle = ROAD_IDLE;
      ctx.lineWidth = 0.6;
      ctx.globalAlpha = 0.55;
      ctx.beginPath();
      for (const e of layout.edges) {
        const path = layout.edgePaths.get(e.key);
        if (path === undefined || path.length < 2) continue;
        for (let i = 0; i < path.length; i++) {
          const p = path[i];
          if (p === undefined) continue;
          const x = p[0] * CELL + CELL / 2;
          const y = p[1] * CELL + CELL / 2;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
      ctx.globalAlpha = 1;

      // Then overlay any HOT edges (recent traffic) along their A* path.
      for (const e of layout.edges) {
        const heat = edgeHeatRef.current.get(e.key) ?? 0;
        if (heat < HEAT_MIN_VISIBLE) continue;
        const path = layout.edgePaths.get(e.key);
        if (path === undefined || path.length < 2) continue;
        const color = lerpColor(ROAD_IDLE, ROAD_HOT, heat);
        ctx.strokeStyle = color;
        ctx.lineWidth = 0.8 + heat * 2.4;
        ctx.globalAlpha = 0.35 + heat * 0.65;
        ctx.beginPath();
        for (let i = 0; i < path.length; i++) {
          const p = path[i];
          if (p === undefined) continue;
          const x = p[0] * CELL + CELL / 2;
          const y = p[1] * CELL + CELL / 2;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
        // Decay.
        const next = heat * HEAT_DECAY_PER_FRAME;
        if (next < HEAT_MIN_VISIBLE) edgeHeatRef.current.delete(e.key);
        else edgeHeatRef.current.set(e.key, next);
      }
      ctx.globalAlpha = 1;

      // Cities + goals.
      const goalSet = new Set(topology?.goals ?? []);
      ctx.textBaseline = "middle";
      ctx.textAlign = "center";
      for (const [nodeId, [col, row]] of layout.nodeCells.entries()) {
        const x = col * CELL + CELL / 2;
        const y = row * CELL + CELL / 2;
        const isGoal = goalSet.has(nodeId);
        if (isGoal) {
          // Soft halo.
          ctx.fillStyle = GOAL_HALO;
          ctx.beginPath();
          ctx.arc(x, y, CELL * 2.2, 0, Math.PI * 2);
          ctx.fill();
        }
        // Background tile.
        ctx.fillStyle = isGoal ? GOAL_BG : CITY_BG;
        ctx.fillRect(x - CELL * 0.7, y - CELL * 0.7, CELL * 1.4, CELL * 1.4);
        ctx.strokeStyle = isGoal ? GOAL_FG : "#454854";
        ctx.lineWidth = 1;
        ctx.strokeRect(x - CELL * 0.7, y - CELL * 0.7, CELL * 1.4, CELL * 1.4);
        // Glyph.
        ctx.font = FONT_CITY;
        ctx.fillStyle = isGoal ? GOAL_FG : CITY_FG;
        ctx.fillText(isGoal ? "★" : "■", x, y + 0.5);
        // Label.
        ctx.font = `${CELL - 4}px "JetBrains Mono", monospace`;
        ctx.fillStyle = isGoal ? GOAL_FG : "#7a7d87";
        ctx.fillText(isGoal ? `goal ${nodeId}` : `#${nodeId}`, x, y + CELL * 1.4);
      }

      // Agents — orbit-cluster around their current city.
      const now = performance.now();
      ctx.font = FONT_AGENT;
      ctx.textBaseline = "middle";
      ctx.textAlign = "center";
      // First group agents by their CURRENT node (the position from the
      // last simulation frame). Then for each group, lay them out in
      // expanding rings of 8 so a 50-agent collapse fans out instead of
      // stacking into a single blob.
      const byNode = new Map<number, number[]>();
      const agentPositions = lastFrame?.agent_positions ?? {};
      for (const [idStr, nodeId] of Object.entries(agentPositions)) {
        const arr = byNode.get(nodeId) ?? [];
        arr.push(Number(idStr));
        byNode.set(nodeId, arr);
      }
      // For each agent, decide its render coords.
      for (const [nodeId, agentIds] of byNode.entries()) {
        const cell = layout.nodeCells.get(nodeId);
        if (cell === undefined) continue;
        const cxCity = cell[0] * CELL + CELL / 2;
        const cyCity = cell[1] * CELL + CELL / 2;
        const sorted = [...agentIds].sort((a, b) => a - b);
        sorted.forEach((aid, idx) => {
          // Compute base orbit position. If the agent has an active
          // walk animation we override with that interpolated position.
          let x = cxCity;
          let y = cyCity;
          const anim = animsRef.current.get(aid);
          if (anim !== undefined) {
            const t = (now - anim.startedAt) / anim.durationMs;
            if (t >= 1) animsRef.current.delete(aid);
            else {
              const u = Math.max(0, Math.min(1, t));
              const fi = u * (anim.pathPx.length - 1);
              const i0 = Math.floor(fi);
              const i1 = Math.min(anim.pathPx.length - 1, i0 + 1);
              const frac = fi - i0;
              const p0 = anim.pathPx[i0];
              const p1 = anim.pathPx[i1];
              if (p0 !== undefined && p1 !== undefined) {
                x = p0[0] + (p1[0] - p0[0]) * frac;
                y = p0[1] + (p1[1] - p0[1]) * frac;
              }
            }
          } else if (agentIds.length === 1) {
            x = cxCity;
            y = cyCity;
          } else {
            // Orbit in expanding rings of AGENTS_PER_RING.
            const ring = Math.floor(idx / AGENTS_PER_RING);
            const posInRing = idx % AGENTS_PER_RING;
            const ringRadius = AGENT_RING_INNER + ring * AGENT_RING_STEP;
            // Stagger the angular offset slightly per ring so adjacent
            // rings don't visually align.
            const angle = (posInRing / AGENTS_PER_RING) * Math.PI * 2 - Math.PI / 2 + ring * 0.42;
            x = cxCity + ringRadius * Math.cos(angle);
            y = cyCity + ringRadius * Math.sin(angle);
          }
          // Backing dot to lift the @ off the terrain (stronger now).
          ctx.fillStyle = "rgba(10, 12, 16, 0.85)";
          ctx.beginPath();
          ctx.arc(x, y, CELL * 0.7, 0, Math.PI * 2);
          ctx.fill();
          // Faint colored ring for outline.
          ctx.strokeStyle = agentColor(aid);
          ctx.lineWidth = 1.2;
          ctx.globalAlpha = 0.6;
          ctx.beginPath();
          ctx.arc(x, y, CELL * 0.7, 0, Math.PI * 2);
          ctx.stroke();
          ctx.globalAlpha = 1;
          // The @ glyph.
          ctx.fillStyle = agentColor(aid);
          ctx.fillText("@", x, y + 0.5);
        });
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [layout, lastFrame, topology]);

  if (topology === null || layout === null) {
    return (
      <div className="flex h-full w-full items-center justify-center text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
        world generating<span className="animate-pulse">…</span>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
      <canvas
        ref={terrainCanvasRef}
        className="pointer-events-none absolute inset-0 h-full w-full"
        style={{ imageRendering: "pixelated", objectFit: "contain" }}
        aria-hidden
      />
      <canvas
        ref={liveCanvasRef}
        className="relative h-full w-full"
        style={{ imageRendering: "pixelated", objectFit: "contain" }}
        role="img"
        aria-label="Penumbra world tilemap"
      />
    </div>
  );
}
