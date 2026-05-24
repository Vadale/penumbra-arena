/**
 * useBrushSelection — drag-to-select a time window on an SVG chart.
 *
 * Concept taught: a "brush" is just a 1-D rectangular selection that
 * the user paints with the mouse. We attach a transparent overlay rect
 * to the chart's SVG, listen for pointerdown / pointermove / pointerup
 * on that overlay, and translate pixel ranges back to DATA coordinates
 * via the caller-supplied inverse scale. The caller then filters its
 * data by the returned range and re-derives stats from the slice.
 *
 * We deliberately do NOT depend on d3-brush even though d3 is in the
 * workspace: d3-brush is ~40 KB of imperative DOM mutation that fights
 * React's reconciler, and a 30-line pointer-event handler gives us
 * exactly the affordances we need (start, end, clear) with full TS
 * strictness and zero ref-juggling.
 *
 * Usage:
 *   const svgRef = useRef<SVGSVGElement | null>(null);
 *   const { range, clear, overlay } = useBrushSelection(
 *     svgRef,
 *     (t: number) => sx(t),
 *     (px: number) => invertSx(px),
 *     { x: M.left, y: M.top, width: plotW, height: plotH },
 *   );
 *   const filtered = range
 *     ? data.filter((d) => d.t >= range.start && d.t <= range.end)
 *     : data;
 *   return <svg ref={svgRef}>...{overlay}</svg>;
 */

import { type ReactNode, type RefObject, useCallback, useEffect, useState } from "react";

export interface BrushBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface BrushRange<T extends number> {
  start: T;
  end: T;
}

export interface BrushSelection<T extends number> {
  range: BrushRange<T> | null;
  clear: () => void;
  overlay: ReactNode;
}

interface DragState {
  startPx: number;
  currentPx: number;
}

/**
 * Hook returns { range, clear, overlay }. Embed `overlay` inside the
 * SVG (as the last child, on top of the chart) and the brush will work.
 */
export function useBrushSelection<T extends number>(
  svgRef: RefObject<SVGSVGElement | null>,
  xScale: (v: T) => number,
  invertX: (px: number) => T,
  bounds: BrushBounds,
): BrushSelection<T> {
  const [drag, setDrag] = useState<DragState | null>(null);
  const [range, setRange] = useState<BrushRange<T> | null>(null);

  const clear = useCallback(() => {
    setRange(null);
    setDrag(null);
  }, []);

  // viewBox <-> client coords via SVG CTM inversion. Falls back to
  // bounding-rect proportional scaling if CTM isn't available (jsdom).
  const clientToViewBoxX = useCallback(
    (clientX: number): number => {
      const svg = svgRef.current;
      if (!svg) return 0;
      const ctm = typeof svg.getScreenCTM === "function" ? svg.getScreenCTM() : null;
      if (ctm && typeof svg.createSVGPoint === "function") {
        const pt = svg.createSVGPoint();
        pt.x = clientX;
        pt.y = 0;
        const local = pt.matrixTransform(ctm.inverse());
        return local.x;
      }
      const rect = svg.getBoundingClientRect();
      if (rect.width === 0) return clientX;
      const vb = svg.viewBox?.baseVal;
      const vbW = vb && vb.width > 0 ? vb.width : rect.width;
      const vbX = vb ? vb.x : 0;
      return vbX + ((clientX - rect.left) / rect.width) * vbW;
    },
    [svgRef],
  );

  const clamp = useCallback(
    (px: number): number => {
      const lo = bounds.x;
      const hi = bounds.x + bounds.width;
      if (px < lo) return lo;
      if (px > hi) return hi;
      return px;
    },
    [bounds.x, bounds.width],
  );

  useEffect(() => {
    if (drag === null) return;
    const onMove = (e: PointerEvent) => {
      const px = clamp(clientToViewBoxX(e.clientX));
      setDrag((prev) => (prev === null ? prev : { ...prev, currentPx: px }));
    };
    const onUp = (e: PointerEvent) => {
      const px = clamp(clientToViewBoxX(e.clientX));
      setDrag((prev) => {
        if (prev === null) return prev;
        const lo = Math.min(prev.startPx, px);
        const hi = Math.max(prev.startPx, px);
        if (hi - lo < 4) {
          setRange(null);
        } else {
          const start = invertX(lo);
          const end = invertX(hi);
          const ordered: BrushRange<T> = start <= end ? { start, end } : { start: end, end: start };
          setRange(ordered);
        }
        return null;
      });
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [drag, clamp, clientToViewBoxX, invertX]);

  const onPointerDown = useCallback(
    (e: React.PointerEvent<SVGRectElement>) => {
      if (e.button !== 0) return;
      const px = clamp(clientToViewBoxX(e.clientX));
      setDrag({ startPx: px, currentPx: px });
    },
    [clamp, clientToViewBoxX],
  );

  const liveLo = drag ? Math.min(drag.startPx, drag.currentPx) : null;
  const liveHi = drag ? Math.max(drag.startPx, drag.currentPx) : null;
  const rangeLo = range ? xScale(range.start) : null;
  const rangeHi = range ? xScale(range.end) : null;

  const overlay: ReactNode = (
    <g data-testid="brush-overlay">
      {rangeLo !== null && rangeHi !== null && (
        <rect
          data-testid="brush-range"
          x={rangeLo}
          y={bounds.y}
          width={Math.max(0, rangeHi - rangeLo)}
          height={bounds.height}
          fill="color-mix(in srgb, var(--color-penumbra-cyan) 12%, transparent)"
          stroke="var(--color-penumbra-cyan)"
          strokeWidth={0.5}
          strokeDasharray="2 2"
          pointerEvents="none"
        />
      )}
      {liveLo !== null && liveHi !== null && (
        <rect
          data-testid="brush-live"
          x={liveLo}
          y={bounds.y}
          width={Math.max(0, liveHi - liveLo)}
          height={bounds.height}
          fill="color-mix(in srgb, var(--color-penumbra-cyan) 22%, transparent)"
          pointerEvents="none"
        />
      )}
      <rect
        data-testid="brush-capture"
        x={bounds.x}
        y={bounds.y}
        width={bounds.width}
        height={bounds.height}
        fill="transparent"
        cursor="crosshair"
        onPointerDown={onPointerDown}
      />
    </g>
  );

  return { range, clear, overlay };
}

/**
 * Compute mean / std / min / max / last for a number array. Exported
 * so charts that want the brush stats card can stay DRY.
 */
export interface WindowStats {
  n: number;
  mean: number;
  std: number;
  min: number;
  max: number;
  last: number;
}

export function windowStats(values: readonly number[]): WindowStats | null {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return null;
  let sum = 0;
  let min = finite[0] as number;
  let max = finite[0] as number;
  for (const v of finite) {
    sum += v;
    if (v < min) min = v;
    if (v > max) max = v;
  }
  const mean = sum / finite.length;
  let sq = 0;
  for (const v of finite) sq += (v - mean) ** 2;
  const std = Math.sqrt(sq / finite.length);
  return {
    n: finite.length,
    mean,
    std,
    min,
    max,
    last: finite[finite.length - 1] as number,
  };
}
