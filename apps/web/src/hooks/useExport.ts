/**
 * useExport — chart-data export hook.
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
 *       contains an <svg>. The SVG is serialised, drawn onto a
 *       canvas, and exported as a PNG blob. Pure-DOM, no deps.
 */

import { useCallback, useState } from "react";

export type ExportFormat = "csv" | "json" | "png" | "notebook";

const EXTENSION: Record<ExportFormat, string> = {
  csv: "csv",
  json: "json",
  png: "png",
  notebook: "ipynb",
};

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
 * Render an SVG inside the given element to a PNG and trigger a
 * download. If the element contains a <canvas>, export that instead.
 *
 * Throws if no <svg> nor <canvas> is found inside `chartElement`.
 */
export async function downloadChartAsPng(
  chartElement: HTMLElement | SVGElement,
  filename: string,
): Promise<void> {
  const canvas = findCanvas(chartElement);
  if (canvas) {
    const blob = await canvasToBlob(canvas);
    triggerBlobDownload(blob, filename);
    return;
  }
  const svg = findSvg(chartElement);
  if (!svg) {
    throw new Error("no <svg> or <canvas> found inside chart element");
  }
  const blob = await svgToPngBlob(svg);
  triggerBlobDownload(blob, filename);
}

function findSvg(root: HTMLElement | SVGElement): SVGSVGElement | null {
  if (root instanceof SVGSVGElement) return root;
  return root.querySelector("svg");
}

function findCanvas(root: HTMLElement | SVGElement): HTMLCanvasElement | null {
  if (root instanceof HTMLCanvasElement) return root;
  return root.querySelector("canvas");
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("canvas.toBlob returned null"));
    }, "image/png");
  });
}

async function svgToPngBlob(svg: SVGSVGElement): Promise<Blob> {
  const { width, height } = measureSvg(svg);
  const cloned = svg.cloneNode(true) as SVGSVGElement;
  cloned.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  if (!cloned.getAttribute("width")) cloned.setAttribute("width", String(width));
  if (!cloned.getAttribute("height")) cloned.setAttribute("height", String(height));
  const xml = new XMLSerializer().serializeToString(cloned);
  const svgBlob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);
  try {
    const image = await loadImage(url);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width));
    canvas.height = Math.max(1, Math.round(height));
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2D canvas context unavailable");
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
