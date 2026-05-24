/**
 * useExport - chart-data export hook.
 *
 * Concept taught: how to wire a typed React hook to a server-side
 * file-download endpoint without leaking blob URLs, and how to fall
 * back to client-side SVG rasterisation when no server route exists
 * for a given chart.
 *
 * Two surfaces:
 *  1. useExport(metric).download(format)
 *       hits GET /export/chart/{metric}?format={csv|json|png}
 *       (or /export/notebook?metric={metric} for "notebook")
 *       and triggers the standard hidden-<a>.click() browser
 *       file-download dance.
 *  2. downloadChartAsPng(element, filename)
 *       client-side fallback for any chart whose root DOM node
 *       contains an <svg>, <canvas>, or any other visible content.
 *       The largest SVG/canvas descendant is picked, rescaled to a
 *       readable 800x400 target, given an opaque dark background
 *       so it doesn't look broken on white pages, and exported
 *       as a PNG blob. Pure-DOM, no deps.
 */

import { useCallback, useState } from "react";

export type ExportFormat = "csv" | "json" | "png" | "notebook";

const EXTENSION: Record<ExportFormat, string> = {
  csv: "csv",
  json: "json",
  png: "png",
  notebook: "ipynb",
};

// Target raster dimensions for the client-side fallback. Matches the
// server-side matplotlib output so screenshots from the two paths look
// the same size in a writeup. The penumbra dark-blue background keeps
// the PNG legible on a light README/page.
const TARGET_WIDTH = 800;
const TARGET_HEIGHT = 400;
const TARGET_BG = "#0c1c20";

function buildExportUrl(metric: string, format: ExportFormat): string {
  if (format === "notebook") {
    return `/export/notebook?metric=${encodeURIComponent(metric)}`;
  }
  return `/export/chart/${encodeURIComponent(metric)}?format=${format}`;
}

function errorMessage(exc: unknown): string {
  if (exc instanceof Error) return exc.message;
  return String(exc);
}

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.rel = "noopener";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export interface UseExportResult {
  download: (format: ExportFormat) => Promise<void>;
  isExporting: boolean;
  error: string | null;
}

export function useExport(metric: string): UseExportResult {
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = useCallback(
    async (format: ExportFormat): Promise<void> => {
      setIsExporting(true);
      setError(null);
      const url = buildExportUrl(metric, format);
      try {
        const res = await fetch(url, { headers: { accept: "*/*" } });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status} on ${url}`);
        }
        const blob = await res.blob();
        const filename = `${metric}.${EXTENSION[format]}`;
        triggerBlobDownload(blob, filename);
      } catch (exc) {
        setError(errorMessage(exc));
      } finally {
        setIsExporting(false);
      }
    },
    [metric],
  );

  return { download, isExporting, error };
}

/**
 * Render the largest SVG/canvas inside the given element to an opaque
 * 800x400 PNG and trigger a download. Falls back to rasterising the
 * entire element on a scaled canvas (foreignObject SVG) when no SVG or
 * canvas exists.
 *
 * Throws if rasterisation fails for any reason.
 */
export async function downloadChartAsPng(
  chartElement: HTMLElement | SVGElement,
  filename: string,
): Promise<void> {
  const canvas = findLargestCanvas(chartElement);
  if (canvas) {
    const blob = await rasterCanvasToBlob(canvas);
    triggerBlobDownload(blob, filename);
    return;
  }
  const svg = findLargestSvg(chartElement);
  if (svg) {
    const blob = await svgToPngBlob(svg);
    triggerBlobDownload(blob, filename);
    return;
  }
  if (chartElement instanceof HTMLElement) {
    const blob = await elementToPngBlob(chartElement);
    triggerBlobDownload(blob, filename);
    return;
  }
  throw new Error("no rasterisable content found inside chart element");
}

function elementArea(el: Element): number {
  const rect = el.getBoundingClientRect();
  return rect.width * rect.height;
}

function findLargestSvg(root: HTMLElement | SVGElement): SVGSVGElement | null {
  if (root instanceof SVGSVGElement) return root;
  const all = Array.from(root.querySelectorAll<SVGSVGElement>("svg"));
  if (all.length === 0) return null;
  return all.reduce((best, cur) => (elementArea(cur) > elementArea(best) ? cur : best));
}

function findLargestCanvas(root: HTMLElement | SVGElement): HTMLCanvasElement | null {
  if (root instanceof HTMLCanvasElement) return root;
  const all = Array.from(root.querySelectorAll<HTMLCanvasElement>("canvas"));
  if (all.length === 0) return null;
  return all.reduce((best, cur) => (elementArea(cur) > elementArea(best) ? cur : best));
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("canvas.toBlob returned null"));
    }, "image/png");
  });
}

async function rasterCanvasToBlob(source: HTMLCanvasElement): Promise<Blob> {
  // Source canvases (e.g. r3f) often render at their on-screen size,
  // which can be tiny. Re-raster onto our standard 800x400 target so
  // the downloaded image is readable.
  const out = document.createElement("canvas");
  out.width = TARGET_WIDTH;
  out.height = TARGET_HEIGHT;
  const ctx = out.getContext("2d");
  if (!ctx) throw new Error("2D canvas context unavailable");
  ctx.fillStyle = TARGET_BG;
  ctx.fillRect(0, 0, out.width, out.height);
  const { dx, dy, dw, dh } = fitInto(source.width, source.height, out.width, out.height);
  ctx.drawImage(source, dx, dy, dw, dh);
  return await canvasToBlob(out);
}

function fitInto(
  sw: number,
  sh: number,
  dw: number,
  dh: number,
): { dx: number; dy: number; dw: number; dh: number } {
  if (sw <= 0 || sh <= 0) return { dx: 0, dy: 0, dw, dh };
  const scale = Math.min(dw / sw, dh / sh);
  const w = Math.max(1, Math.round(sw * scale));
  const h = Math.max(1, Math.round(sh * scale));
  const dx = Math.floor((dw - w) / 2);
  const dy = Math.floor((dh - h) / 2);
  return { dx, dy, dw: w, dh: h };
}

async function svgToPngBlob(svg: SVGSVGElement): Promise<Blob> {
  const { width: srcW, height: srcH } = measureSvg(svg);
  const cloned = svg.cloneNode(true) as SVGSVGElement;
  cloned.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  // Preserve aspect ratio: rescale the SVG to fill an 800x400 viewport
  // while keeping its viewBox. If the SVG has no viewBox, install one
  // based on its current pixel size so the rasteriser doesn't crop.
  let viewBox = cloned.getAttribute("viewBox");
  if (!viewBox) {
    viewBox = `0 0 ${srcW} ${srcH}`;
    cloned.setAttribute("viewBox", viewBox);
  }
  cloned.setAttribute("width", String(TARGET_WIDTH));
  cloned.setAttribute("height", String(TARGET_HEIGHT));
  cloned.setAttribute("preserveAspectRatio", "xMidYMid meet");
  const xml = new XMLSerializer().serializeToString(cloned);
  const svgBlob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);
  try {
    const image = await loadImage(url);
    const canvas = document.createElement("canvas");
    canvas.width = TARGET_WIDTH;
    canvas.height = TARGET_HEIGHT;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2D canvas context unavailable");
    ctx.fillStyle = TARGET_BG;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    return await canvasToBlob(canvas);
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function elementToPngBlob(element: HTMLElement): Promise<Blob> {
  // Wrap the element's HTML in a foreignObject inside an SVG so it can
  // be rendered onto a canvas. Browsers refuse to draw a foreignObject
  // containing cross-origin resources, but our tiles render local CSS
  // and text only, so this works for the "Stat number + tiny sparkline"
  // shape (e.g. trajectory_mean) that the client fallback previously
  // captured as a black slab.
  const rect = element.getBoundingClientRect();
  const srcW = Math.max(1, Math.round(rect.width || 320));
  const srcH = Math.max(1, Math.round(rect.height || 120));
  const cloned = element.cloneNode(true) as HTMLElement;
  cloned.style.width = `${srcW}px`;
  cloned.style.height = `${srcH}px`;
  cloned.style.background = TARGET_BG;
  cloned.style.color = "#e6f0f1";
  const wrapper = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${TARGET_WIDTH}" height="${TARGET_HEIGHT}" viewBox="0 0 ${srcW} ${srcH}">
  <foreignObject width="100%" height="100%">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:ui-monospace,monospace;font-size:12px;color:#e6f0f1;background:${TARGET_BG};width:${srcW}px;height:${srcH}px;">
      ${cloned.outerHTML}
    </div>
  </foreignObject>
</svg>`;
  const blob = new Blob([wrapper], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  try {
    const image = await loadImage(url);
    const canvas = document.createElement("canvas");
    canvas.width = TARGET_WIDTH;
    canvas.height = TARGET_HEIGHT;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2D canvas context unavailable");
    ctx.fillStyle = TARGET_BG;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    return await canvasToBlob(canvas);
  } finally {
    URL.revokeObjectURL(url);
  }
}

function measureSvg(svg: SVGSVGElement): { width: number; height: number } {
  const rect = svg.getBoundingClientRect();
  const w = rect.width || Number(svg.getAttribute("width")) || 640;
  const h = rect.height || Number(svg.getAttribute("height")) || 360;
  return { width: w, height: h };
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("failed to rasterise SVG"));
    img.src = src;
  });
}
