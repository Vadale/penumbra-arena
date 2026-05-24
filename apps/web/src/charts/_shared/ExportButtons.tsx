/**
 * ExportButtons — inline CSV / JSON / PNG / Jupyter-notebook export
 * controls for a single metric.
 *
 * Concept taught: how to expose a server-side file-download endpoint
 * through a tiny, accessible button row. Each button is a ghost
 * control that pipes its format through `useExport(metric)`; the
 * in-flight state collapses the row into a spinner and any error
 * surfaces inline below the buttons (consistent with FetchError).
 */

import type { ExportFormat } from "../../hooks/useExport";
import { useExport } from "../../hooks/useExport";

interface Props {
  metric: string;
}

const FORMATS: readonly { format: ExportFormat; label: string }[] = [
  { format: "csv", label: "csv" },
  { format: "json", label: "json" },
  { format: "png", label: "png" },
  { format: "notebook", label: "ipynb" },
];

export function ExportButtons({ metric }: Props) {
  const { download, isExporting, error } = useExport(metric);

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
        <span aria-hidden="true">{"↓"}</span>
        <span>export:</span>
        {isExporting ? (
          <span
            role="status"
            aria-live="polite"
            className="font-mono text-[color:var(--color-penumbra-cyan)]"
          >
            exporting...
          </span>
        ) : (
          FORMATS.map(({ format, label }) => (
            <button
              key={format}
              type="button"
              onClick={() => {
                void download(format);
              }}
              disabled={isExporting}
              aria-label={`Export ${metric} as ${label}`}
              className="border border-[color:var(--color-penumbra-border)] bg-transparent px-2 py-[2px] font-mono text-[10px] uppercase text-[color:var(--color-penumbra-muted)] hover:border-[color:var(--color-penumbra-cyan)] hover:text-[color:var(--color-penumbra-cyan)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {label}
            </button>
          ))
        )}
      </div>
      {error ? (
        <div className="font-mono text-[10px] text-[color:var(--color-penumbra-ember)]">
          export failed: {error}
        </div>
      ) : null}
    </div>
  );
}
