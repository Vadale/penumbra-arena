/**
 * Modal that pops up when the user clicks an AnalyticsPanel cell.
 *
 * Owns: dialog frame, focus trap, Escape/backdrop dismiss, export
 * controls, trigger-event section. Per-metric chart rendering lives
 * in `DetailModalBody.tsx`; static metric metadata (labels,
 * descriptions, CLI hints, export allow-list, inject mapping) lives
 * in `DetailModalMeta.ts`.
 *
 * Dismiss via Escape, backdrop click, or the explicit close button.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { downloadChartAsPng } from "../hooks/useExport";
import { useFocusTrap } from "../hooks/useFocusTrap";
import { useAchievementsStore } from "../stores/achievements";
import type {
  ANOVAReport as ANOVAReportData,
  ArimaForecast as ArimaForecastData,
  AutocorrelationReport as AutocorrelationReportData,
  BayesianPosterior as BayesianPosteriorData,
  CandleSeries as CandleSeriesData,
  CausalEstimate as CausalEstimateData,
  ClusterScatter as ClusterScatterData,
  CorrelationMatrix as CorrelationMatrixData,
  EconomySnapshot as EconomySnapshotData,
  GarchResult as GarchResultData,
  GrangerMatrix as GrangerMatrixData,
  InflationSeries as InflationSeriesData,
  LogitResult as LogitResultData,
  MonteCarloFan as MCFanData,
  PCAResult,
  PermutationReport as PermutationReportData,
  RegressionFit,
  ROCData as ROCDataType,
  SpectralReport as SpectralReportData,
  SurvivalCurve as SurvivalCurveData,
  VARImpulseResponse as VARImpulseResponseData,
  WealthReport as WealthReportData,
} from "../streams/dashboard";
import { ExportButtons } from "./_shared";
import { InjectBlockAgentForm, InjectTriggerButton } from "./_shared/InjectTriggerButton";
import { MetricBody } from "./DetailModalBody";
import { EXPORTABLE, INJECT_TRIGGERS, META, type MetricKind } from "./DetailModalMeta";

export type { MetricKind } from "./DetailModalMeta";

interface Props {
  open: boolean;
  onClose: () => void;
  metric: MetricKind | null;
  values?: number[];
  topicSizes?: Record<string, number>;
  topicTopWords?: Record<string, string[]>;
  regression?: RegressionFit | null;
  clusterScatter?: ClusterScatterData | null;
  monteCarlo?: MCFanData | null;
  pca?: PCAResult | null;
  arima?: ArimaForecastData | null;
  logit?: LogitResultData | null;
  bayesian?: BayesianPosteriorData | null;
  granger?: GrangerMatrixData | null;
  economy?: EconomySnapshotData | null;
  survival?: SurvivalCurveData | null;
  spectral?: SpectralReportData | null;
  causal?: CausalEstimateData | null;
  varIrf?: VARImpulseResponseData | null;
  garch?: GarchResultData | null;
  qqPoints?: [number, number][];
  residualVsFitted?: [number, number][];
  anova?: ANOVAReportData | null;
  autocorrelation?: AutocorrelationReportData | null;
  roc?: ROCDataType | null;
  correlations?: CorrelationMatrixData | null;
  permutation?: PermutationReportData | null;
  candles?: CandleSeriesData[];
  inflation?: InflationSeriesData | null;
  wealth?: WealthReportData | null;
}

export function DetailModal(props: Props) {
  const { open, onClose, metric } = props;
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const [pngError, setPngError] = useState<string | null>(null);
  const markTileOpened = useAchievementsStore((s) => s.markTileOpened);
  useFocusTrap(dialogRef, open && metric !== null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
    };
  }, [open, onClose]);

  useEffect(() => {
    if (open && metric !== null) {
      markTileOpened(metric);
    }
  }, [open, metric, markTileOpened]);

  const handleClientPng = useCallback(async (kind: MetricKind) => {
    setPngError(null);
    const element = chartContainerRef.current;
    if (!element) {
      setPngError("chart not yet mounted");
      return;
    }
    try {
      await downloadChartAsPng(element, `${kind}.png`);
    } catch (exc) {
      setPngError(exc instanceof Error ? exc.message : String(exc));
    }
  }, []);

  if (!open || metric === null) return null;
  const meta = META[metric];
  const supportsServerExport = EXPORTABLE.has(metric);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6">
      {/* Backdrop: clickable to dismiss, but hidden from screen readers so the */}
      {/* dialog content is announced first; the explicit "Close" button is the */}
      {/* SR-discoverable dismiss. Esc also dismisses via the effect above. */}
      <div
        aria-hidden="true"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-transparent"
      />
      <div
        ref={dialogRef}
        className="relative w-full max-w-2xl border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] p-5 shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label={meta.label}
      >
        <div className="mb-3 flex items-baseline justify-between">
          <div className="text-xs uppercase tracking-[0.25em] text-[color:var(--color-penumbra-cyan)]">
            {meta.label}
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="text-[14px] leading-none text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-text)]"
          >
            {"×"}
          </button>
        </div>
        <p className="mb-4 text-[11px] leading-relaxed text-[color:var(--color-penumbra-muted)]">
          {meta.description}
        </p>
        {meta.cli && (
          <div className="mb-4 border-l-2 border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-bg)] px-3 py-2">
            <div className="mb-1 text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-muted)]">
              try it in your shell
            </div>
            <code className="block whitespace-pre-wrap break-all font-mono text-[11px] text-[color:var(--color-penumbra-cyan)]">
              {meta.cli}
            </code>
          </div>
        )}
        <div className="mb-2 flex items-start justify-between gap-2">
          {supportsServerExport ? (
            <ExportButtons metric={metric} />
          ) : (
            <div className="text-[10px] text-[color:var(--color-penumbra-muted)]">
              Export not yet supported for this metric — open the underlying endpoint via the
              Try-in-shell hint above.
            </div>
          )}
          <div className="flex flex-col items-end gap-1">
            <button
              type="button"
              onClick={() => {
                void handleClientPng(metric);
              }}
              aria-label="Download chart as PNG"
              className="border border-[color:var(--color-penumbra-border)] bg-transparent px-2 py-[2px] font-mono text-[10px] uppercase text-[color:var(--color-penumbra-muted)] hover:border-[color:var(--color-penumbra-cyan)] hover:text-[color:var(--color-penumbra-cyan)]"
            >
              {"↓ download as png"}
            </button>
            {pngError ? (
              <div className="font-mono text-[10px] text-[color:var(--color-penumbra-ember)]">
                png export failed: {pngError}
              </div>
            ) : null}
          </div>
        </div>
        <div
          ref={chartContainerRef}
          className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-3"
        >
          <MetricBody {...props} metric={metric} meta={meta} />
        </div>
        <TriggerSection metric={metric} />
      </div>
    </div>
  );
}

function TriggerSection({ metric }: { metric: MetricKind }) {
  const mapping = INJECT_TRIGGERS[metric];
  const showBlockForm = metric === "security_blocked";
  if (!mapping && !showBlockForm) return null;
  return (
    <div className="mt-3 border-t border-[color:var(--color-penumbra-border)] pt-2">
      <div className="mb-1 text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-dim)]">
        trigger this event
      </div>
      {mapping && (
        <InjectTriggerButton label={mapping.label} kind={mapping.kind} payload={mapping.payload} />
      )}
      {showBlockForm && <InjectBlockAgentForm />}
    </div>
  );
}
