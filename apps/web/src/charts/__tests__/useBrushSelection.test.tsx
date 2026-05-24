// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { act, useRef } from "react";
import { describe, expect, it } from "vitest";
import { useBrushSelection, windowStats } from "../../hooks/useBrushSelection";

// jsdom 25 does not implement PointerEvent. Our hook listens for
// pointerdown/pointermove/pointerup, which are valid event types
// regardless of which constructor produced them — a MouseEvent with
// type "pointermove" dispatched on window fires the same listeners
// because the hook reads .clientX and not pointer-specific fields.
function makePointerEvent(
  type: string,
  init: { clientX: number; clientY: number; button?: number },
): Event {
  const evt = new MouseEvent(type, {
    bubbles: true,
    cancelable: true,
    clientX: init.clientX,
    clientY: init.clientY,
    button: init.button ?? 0,
  });
  return evt;
}

function pointerDown(el: Element, clientX: number) {
  el.dispatchEvent(makePointerEvent("pointerdown", { clientX, clientY: 10 }));
}

function pointerMove(clientX: number) {
  window.dispatchEvent(makePointerEvent("pointermove", { clientX, clientY: 10 }));
}

function pointerUp(clientX: number) {
  window.dispatchEvent(makePointerEvent("pointerup", { clientX, clientY: 10 }));
}

/**
 * Test harness: a 100-pixel-wide brush over the data domain [0, 100].
 * Identity scale + identity inverse keep math obvious.
 *
 * jsdom does not implement getScreenCTM / createSVGPoint reliably, so
 * the hook falls back to getBoundingClientRect-based proportional
 * coords. We monkey-patch getBoundingClientRect on the rendered SVG
 * so a clientX of N maps to viewBox-X of N.
 */

const BOUNDS = { x: 0, y: 0, width: 100, height: 50 } as const;

function ProbeHarness() {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const { range, clear, overlay } = useBrushSelection<number>(
    svgRef,
    (v) => v,
    (px) => px,
    BOUNDS,
  );

  return (
    <div>
      <svg
        ref={svgRef}
        data-testid="svg"
        viewBox="0 0 100 50"
        width="100"
        height="50"
        role="img"
        aria-label="brush probe"
      >
        {overlay}
      </svg>
      <div data-testid="range">{range === null ? "null" : `${range.start}..${range.end}`}</div>
      <button type="button" data-testid="clear-btn" onClick={clear}>
        clear
      </button>
    </div>
  );
}

function patchBoundingRect(el: Element, rect: Partial<DOMRect>) {
  const full: DOMRect = {
    x: rect.x ?? 0,
    y: rect.y ?? 0,
    width: rect.width ?? 100,
    height: rect.height ?? 50,
    top: rect.y ?? 0,
    left: rect.x ?? 0,
    right: (rect.x ?? 0) + (rect.width ?? 100),
    bottom: (rect.y ?? 0) + (rect.height ?? 50),
    toJSON: () => ({}),
  };
  Object.defineProperty(el, "getBoundingClientRect", {
    configurable: true,
    value: () => full,
  });
}

describe("useBrushSelection", () => {
  it("starts with null range", () => {
    render(<ProbeHarness />);
    expect(screen.getByTestId("range").textContent).toBe("null");
  });

  function setupBrushSvg() {
    render(<ProbeHarness />);
    const svg = screen.getByTestId("svg");
    patchBoundingRect(svg, { x: 0, y: 0, width: 100, height: 50 });
    // jsdom's SVGSVGElement is missing CTM; force fallback path.
    Object.defineProperty(svg, "getScreenCTM", {
      configurable: true,
      value: () => null,
    });
    return screen.getByTestId("brush-capture");
  }

  it("a mousedown -> mousemove -> mouseup drag sets the range", () => {
    const capture = setupBrushSvg();
    act(() => {
      pointerDown(capture, 20);
    });
    act(() => {
      pointerMove(60);
    });
    act(() => {
      pointerUp(60);
    });

    expect(screen.getByTestId("range").textContent).toBe("20..60");
    expect(screen.queryByTestId("brush-range")).not.toBeNull();
  });

  it("clear() resets the range back to null", () => {
    const capture = setupBrushSvg();
    act(() => {
      pointerDown(capture, 10);
    });
    act(() => {
      pointerUp(80);
    });
    expect(screen.getByTestId("range").textContent).toBe("10..80");

    act(() => {
      fireEvent.click(screen.getByTestId("clear-btn"));
    });
    expect(screen.getByTestId("range").textContent).toBe("null");
    expect(screen.queryByTestId("brush-range")).toBeNull();
  });

  it("treats a micro-click (<4 px) as a clear, not a selection", () => {
    const capture = setupBrushSvg();
    act(() => {
      pointerDown(capture, 50);
    });
    act(() => {
      pointerUp(51);
    });
    expect(screen.getByTestId("range").textContent).toBe("null");
  });

  it("clamps a drag that exits the chart bounds to the bounds", () => {
    const capture = setupBrushSvg();
    act(() => {
      pointerDown(capture, 25);
    });
    act(() => {
      pointerUp(250);
    });
    expect(screen.getByTestId("range").textContent).toBe("25..100");
  });
});

describe("windowStats", () => {
  it("returns null for an empty array", () => {
    expect(windowStats([])).toBeNull();
  });

  it("computes mean / std / min / max / n / last", () => {
    const s = windowStats([1, 2, 3, 4, 5]);
    expect(s).not.toBeNull();
    if (s === null) return;
    expect(s.n).toBe(5);
    expect(s.min).toBe(1);
    expect(s.max).toBe(5);
    expect(s.last).toBe(5);
    expect(s.mean).toBeCloseTo(3, 6);
    expect(s.std).toBeCloseTo(Math.sqrt(2), 6);
  });

  it("ignores non-finite values", () => {
    const s = windowStats([1, Number.NaN, 2, Number.POSITIVE_INFINITY, 3]);
    expect(s).not.toBeNull();
    if (s === null) return;
    expect(s.n).toBe(3);
    expect(s.min).toBe(1);
    expect(s.max).toBe(3);
  });
});
