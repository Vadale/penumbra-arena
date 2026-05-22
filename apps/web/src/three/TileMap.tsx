/**
 * Dwarf-Fortress-style tile-map of the Penumbra world.
 *
 * Concept: real territory, not a graph diagram. A 90×54 grid of
 * 12×12 pixel cells; each cell is a single character glyph at a
 * monospace baseline, drawn on a Canvas for throughput.
 *
 * Layers (back to front)
 * 1. Terrain — procedural biome map from two simplex-noise
 *    octaves (elevation + moisture). Each cell maps to one of:
 *      ~ water       (low elevation)
 *      ^ mountain    (high elevation)
 *      T forest      (mid elevation + high moisture)
 *      . grass       (mid elevation + low moisture)
 *      , scrub       (transition between grass and water/mountain)
 *
 * 2. Roads — the arena's graph edges drawn as Bresenham tile-paths
 *    between the cells where their endpoint cities sit. Roads
 *    overwrite terrain with a `#` glyph in a road-color.
 *
 * 3. Cities + goals — every arena node occupies one cell. Goals
 *    use a star glyph in cyan with a halo; ordinary outposts use
 *    a square glyph in muted gray.
 *
 * 4. Agents — every agent is a SINGLE animated `@` glyph (color
 *    derived from id). When the simulation tick changes an agent's
 *    node, the visual position interpolates along the road
 *    connecting the previous node to the current one, tile-by-tile,
 *    at 60 fps. So you see characters WALKING down the roads.
 *
 * Performance — terrain + roads + cities are static given the
 * topology, so they're rasterised ONCE to an offscreen canvas and
 * blitted to the main canvas each animation frame. Agents (50
 * glyphs) are drawn on top per frame. ~1ms/frame total on M4.
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
const FONT_BIG = `${CELL + 2}px "JetBrains Mono", "Fira Code", monospace`;

// Animation: each agent walks at this many tiles per second.
const AGENT_TILE_PER_SEC = 6;

// Tile glyph + foreground colour by biome.
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

const ROAD_FG = "#7a6f3f";
const ROAD_BG = "#251f10";
const CITY_FG = "#cfd2d7";
const CITY_BG = "#252731";
const GOAL_FG = "#86dfe6"; // cyan
const GOAL_BG = "#0e2e33";
const GOAL_HALO = "#1a4a52";

interface TileLayout {
  /** biome[row][col] */
  biome: Biome[][];
  /** isRoad[row][col] */
  isRoad: boolean[][];
  /** Map nodeId -> (col, row) tile centre. */
  nodeCells: Map<number, [number, number]>;
  /** For each edge (u,v) the ordered list of (col,row) tiles forming its road. */
  edgePaths: Map<string, [number, number][]>;
}

/** Stable hue per agent id; golden-ratio spread. */
function agentColor(id: number): string {
  const hue = ((id * 0.6180339887) % 1) * 360;
  return `oklch(0.82 0.18 ${hue.toFixed(1)})`;
}

/** Simple deterministic LCG seeded from PENUMBRA_SEED so the map is stable. */
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

/** Bresenham line between two grid cells; returns ordered list of cells. */
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

/**
 * Lay out nodes by a small force simulation, then snap to grid cells.
 * Spread the world a bit and keep nodes away from borders.
 */
function layoutNodes(
  nodes: number[],
  edges: { u: number; v: number }[],
  rng: () => number,
): Map<number, [number, number]> {
  // Tiny pure-JS force step to spread the nodes. We import d3 lazily
  // to avoid pulling it into the bundle when not needed.
  const pos = new Map<number, { x: number; y: number }>();
  // Initialise on a jittered circle so we don't collapse into the
  // centre under attraction.
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
  // Relax 250 iterations of attraction (linked) + repulsion (all pairs).
  const linkDist = Math.min(COLS, ROWS) * 0.14;
  for (let iter = 0; iter < 250; iter++) {
    // Repulsion (O(N²) but N=50 so fine).
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
    // Attraction along edges.
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
    // Centring + integration.
    for (const id of nodes) {
      const p = pos.get(id);
      const f = forces.get(id);
      if (p === undefined || f === undefined) continue;
      p.x += f.fx + (cx - p.x) * 0.01;
      p.y += f.fy + (cy - p.y) * 0.01;
      // Keep some margin from the world borders.
      p.x = Math.max(3, Math.min(COLS - 4, p.x));
      p.y = Math.max(3, Math.min(ROWS - 4, p.y));
    }
  }
  // Snap to grid cells; resolve collisions by spiralling out.
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
  // Two-octave noise on each channel.
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

  // Build road paths between every edge endpoint.
  const isRoad: boolean[][] = Array.from({ length: ROWS }, () =>
    Array.from({ length: COLS }, () => false),
  );
  const edgePaths = new Map<string, [number, number][]>();
  for (const e of edges) {
    const a = nodeCells.get(e.u);
    const b = nodeCells.get(e.v);
    if (a === undefined || b === undefined) continue;
    const path = bresenham(a[0], a[1], b[0], b[1]);
    edgePaths.set(`${e.u}-${e.v}`, path);
    for (const [col, row] of path) {
      if (col >= 0 && col < COLS && row >= 0 && row < ROWS) {
        const rowArr = isRoad[row];
        if (rowArr !== undefined) rowArr[col] = true;
      }
    }
  }

  return { biome, isRoad, nodeCells, edgePaths };
}

/** Rasterise terrain + roads + cities to an offscreen canvas (once). */
function paintStatic(
  ctx: CanvasRenderingContext2D,
  layout: TileLayout,
  goalSet: Set<number>,
): void {
  ctx.clearRect(0, 0, WIDTH, HEIGHT);
  ctx.textBaseline = "middle";
  ctx.textAlign = "center";
  ctx.font = FONT;

  // Background terrain.
  for (let r = 0; r < ROWS; r++) {
    const biomeRow = layout.biome[r];
    const roadRow = layout.isRoad[r];
    if (biomeRow === undefined || roadRow === undefined) continue;
    for (let c = 0; c < COLS; c++) {
      const tileBiome = biomeRow[c];
      if (tileBiome === undefined) continue;
      const isRoad = roadRow[c] === true;
      const bg = isRoad ? ROAD_BG : BIOME_BG[tileBiome];
      const fg = isRoad ? ROAD_FG : BIOME_FG[tileBiome];
      const glyph = isRoad ? "#" : BIOME_GLYPH[tileBiome];
      ctx.fillStyle = bg;
      ctx.fillRect(c * CELL, r * CELL, CELL, CELL);
      ctx.fillStyle = fg;
      ctx.fillText(glyph, c * CELL + CELL / 2, r * CELL + CELL / 2 + 0.5);
    }
  }

  // Cities + goals on top.
  for (const [nodeId, [col, row]] of layout.nodeCells.entries()) {
    const x = col * CELL + CELL / 2;
    const y = row * CELL + CELL / 2;
    const isGoal = goalSet.has(nodeId);
    // background block
    ctx.fillStyle = isGoal ? GOAL_BG : CITY_BG;
    ctx.fillRect((col - 1) * CELL, (row - 1) * CELL, CELL * 3, CELL * 3);

    if (isGoal) {
      // soft halo via additional translucent square
      ctx.fillStyle = GOAL_HALO;
      ctx.globalAlpha = 0.45;
      ctx.fillRect((col - 2) * CELL, (row - 2) * CELL, CELL * 5, CELL * 5);
      ctx.globalAlpha = 1;
    }

    ctx.font = FONT_BIG;
    ctx.fillStyle = isGoal ? GOAL_FG : CITY_FG;
    ctx.fillText(isGoal ? "★" : "■", x, y + 1);

    // label below
    ctx.font = `${CELL - 4}px "JetBrains Mono", monospace`;
    ctx.fillStyle = isGoal ? GOAL_FG : "#7e828a";
    ctx.fillText(isGoal ? `goal ${nodeId}` : `#${nodeId}`, x, y + CELL * 2);
    ctx.font = FONT;
  }
}

interface AgentAnim {
  /** path of (col, row) tiles to walk over (inclusive of start and end). */
  path: [number, number][];
  /** ms since the walk started. */
  startedAt: number;
  /** total ms the walk should take. */
  durationMs: number;
}

export function TileMap() {
  const topology = useArenaTopology();
  const lastFrame = usePenumbraStore((s) => s.lastFrame);
  const staticCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const liveCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const layoutRef = useRef<TileLayout | null>(null);
  const animsRef = useRef<Map<number, AgentAnim>>(new Map());
  const previousNodesRef = useRef<Map<number, number>>(new Map());

  const layout = useMemo(() => {
    if (topology === null) return null;
    return buildTileLayout(topology.nodes, topology.edges);
  }, [topology]);

  // Paint the static layer when layout / goals change.
  useEffect(() => {
    if (layout === null || topology === null || staticCanvasRef.current === null) return;
    const canvas = staticCanvasRef.current;
    canvas.width = WIDTH;
    canvas.height = HEIGHT;
    const ctx = canvas.getContext("2d");
    if (ctx === null) return;
    paintStatic(ctx, layout, new Set(topology.goals));
    layoutRef.current = layout;
  }, [layout, topology]);

  // Whenever the live frame changes, queue or update agent walk animations.
  useEffect(() => {
    if (lastFrame === null || layout === null) return;
    const now = performance.now();
    for (const [idStr, nodeId] of Object.entries(lastFrame.agent_positions)) {
      const aid = Number(idStr);
      const prevNode = previousNodesRef.current.get(aid);
      if (prevNode === nodeId) continue; // standing still
      // First time we see this agent — just place it, no walk.
      if (prevNode === undefined) {
        previousNodesRef.current.set(aid, nodeId);
        continue;
      }
      // Look up the road path between prev and current node.
      const edgeKeyA = `${prevNode}-${nodeId}`;
      const edgeKeyB = `${nodeId}-${prevNode}`;
      const stored = layout.edgePaths.get(edgeKeyA) ?? layout.edgePaths.get(edgeKeyB);
      let path: [number, number][] = [];
      if (stored !== undefined) {
        path = stored;
        // If the stored path goes the other way, reverse it.
        const first = path[0];
        const expected = layout.nodeCells.get(prevNode);
        if (first !== undefined && expected !== undefined) {
          if (first[0] !== expected[0] || first[1] !== expected[1]) {
            path = [...path].reverse();
          }
        }
      } else {
        // No direct edge (teleport / wrap) — fall back to straight Bresenham.
        const a = layout.nodeCells.get(prevNode);
        const b = layout.nodeCells.get(nodeId);
        if (a !== undefined && b !== undefined) path = bresenham(a[0], a[1], b[0], b[1]);
      }
      if (path.length < 2) {
        previousNodesRef.current.set(aid, nodeId);
        continue;
      }
      const durationMs = (path.length / AGENT_TILE_PER_SEC) * 1000;
      animsRef.current.set(aid, { path, startedAt: now, durationMs });
      previousNodesRef.current.set(aid, nodeId);
    }
  }, [lastFrame, layout]);

  // Animation frame loop: composite the static layer + draw agents on top.
  useEffect(() => {
    if (layout === null) return;
    let raf = 0;
    const tick = () => {
      const live = liveCanvasRef.current;
      const stat = staticCanvasRef.current;
      if (live === null || stat === null) {
        raf = requestAnimationFrame(tick);
        return;
      }
      live.width = WIDTH;
      live.height = HEIGHT;
      const ctx = live.getContext("2d");
      if (ctx === null) {
        raf = requestAnimationFrame(tick);
        return;
      }
      // Blit static layer.
      ctx.clearRect(0, 0, WIDTH, HEIGHT);
      ctx.drawImage(stat, 0, 0);
      // Draw each agent at its interpolated tile position.
      const now = performance.now();
      ctx.font = FONT_BIG;
      ctx.textBaseline = "middle";
      ctx.textAlign = "center";
      const agentPositions = lastFrame?.agent_positions ?? {};
      // Group agents by tile to handle stacking via small offsets.
      const tileCount = new Map<string, number>();
      for (const [idStr, nodeId] of Object.entries(agentPositions)) {
        const aid = Number(idStr);
        const anim = animsRef.current.get(aid);
        let col: number;
        let row: number;
        if (anim !== undefined) {
          const t = Math.min(1, (now - anim.startedAt) / anim.durationMs);
          const idx = Math.min(anim.path.length - 1, Math.floor(t * (anim.path.length - 1)));
          const cell = anim.path[idx];
          if (cell !== undefined) {
            [col, row] = cell;
          } else {
            const here = layout.nodeCells.get(nodeId);
            if (here === undefined) continue;
            [col, row] = here;
          }
          if (t >= 1) animsRef.current.delete(aid);
        } else {
          const here = layout.nodeCells.get(nodeId);
          if (here === undefined) continue;
          [col, row] = here;
        }
        const key = `${col},${row}`;
        const stackIdx = tileCount.get(key) ?? 0;
        tileCount.set(key, stackIdx + 1);
        // Small offset within the cell when stacking.
        const offX = stackIdx === 0 ? 0 : stackIdx % 2 === 0 ? -3 : 3;
        const offY = stackIdx === 0 ? 0 : stackIdx < 3 ? 0 : -3;
        const x = col * CELL + CELL / 2 + offX;
        const y = row * CELL + CELL / 2 + offY + 0.5;
        ctx.fillStyle = agentColor(aid);
        ctx.fillText("@", x, y);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [layout, lastFrame]);

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
        ref={staticCanvasRef}
        className="pointer-events-none absolute inset-0 h-full w-full"
        style={{
          imageRendering: "pixelated",
          objectFit: "contain",
        }}
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
