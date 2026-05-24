/**
 * Live MAPPO training curves: actor/critic loss + entropy + reward + KL.
 *
 * The same MAPPO actor that drives the live arena gets PPO updates
 * from a background trainer. Each iteration appends a row to the
 * curves; the dashboard re-renders so the user can watch the policy
 * mutate in real time. Start/stop with the button.
 *
 * Brush: drag inside any of the four mini-charts to pin an iteration
 * window. All four curves and the per-curve "tail" stats then come
 * from the windowed slice; "× clear selection" restores the full view.
 */

import { useMemo, useRef, useState } from "react";
import { useBrushSelection, windowStats } from "../hooks/useBrushSelection";
import { useFetchJsonPoll } from "../hooks/useFetchJson";
import { BrushStatsCard, FetchError, Stat } from "./_shared";

interface Sample {
  iteration: number;
  actor_loss: number;
  critic_loss: number;
  entropy: number;
  kl: number;
  mean_reward: number;
}

interface CurvesPayload {
  available: boolean;
  samples: Sample[];
  enabled?: boolean;
  iteration?: number;
}

const CURVE_W = 560;
const CURVE_H = 70;
const CURVE_PAD_LEFT = 50;
const CURVE_PAD_RIGHT = 10;

export function TrainingCurves() {
  const state = useFetchJsonPoll<CurvesPayload>("/learning/training/curves", 1500);
  const data =
    state.kind === "data" ? state.value : state.kind === "error" ? state.lastValue : undefined;
  const [busy, setBusy] = useState(false);

  const start = async () => {
    setBusy(true);
    await fetch("/learning/training/start", { method: "POST" });
    setBusy(false);
  };
  const stop = async () => {
    setBusy(true);
    await fetch("/learning/training/stop", { method: "POST" });
    setBusy(false);
  };

  const samples = data?.samples ?? [];
  const enabled = data?.enabled ?? false;
  const iteration = data?.iteration ?? 0;

  // Iteration-domain brush shared by all 4 sub-curves.
  const svgRef = useRef<SVGSVGElement | null>(null);
  const firstIter = samples[0]?.iteration ?? 0;
  const lastIter = samples[samples.length - 1]?.iteration ?? firstIter;
  const iterSpan = Math.max(1, lastIter - firstIter);
  const plotW = CURVE_W - CURVE_PAD_LEFT - CURVE_PAD_RIGHT;
  const sxIter = (it: number) => CURVE_PAD_LEFT + ((it - firstIter) / iterSpan) * plotW;
  const invertIter = (px: number): number => {
    const norm = (px - CURVE_PAD_LEFT) / plotW;
    const clamped = Math.max(0, Math.min(1, norm));
    return Math.round(firstIter + clamped * iterSpan);
  };
  const { range, clear, overlay } = useBrushSelection<number>(svgRef, sxIter, invertIter, {
    x: CURVE_PAD_LEFT,
    y: 0,
    width: plotW,
    height: CURVE_H,
  });

  const filteredSamples = useMemo(() => {
    if (range === null) return samples;
    return samples.filter((s) => s.iteration >= range.start && s.iteration <= range.end);
  }, [range, samples]);

  if (!data?.available) {
    if (state.kind === "error") return <FetchError message={state.message} />;
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        live trainer unavailable (MAPPO checkpoint not loaded)
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      {state.kind === "error" && <FetchError message={state.message} />}
      <div className="grid grid-cols-4 gap-2 text-[10px]">
        <Stat label="iteration" value={String(iteration)} accent />
        <Stat label="samples" value={String(samples.length)} />
        <Stat
          label="status"
          value={enabled ? "TRAINING" : "paused"}
          accent={enabled}
          ember={!enabled}
        />
        <div className="flex items-center justify-end gap-1">
          <button
            type="button"
            onClick={enabled ? stop : start}
            disabled={busy}
            className={
              enabled
                ? "border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)] disabled:opacity-50"
                : "border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] disabled:opacity-50"
            }
          >
            {enabled ? "stop" : "start"}
          </button>
        </div>
      </div>

      {samples.length < 2 ? (
        <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
          {enabled
            ? "training started — first iteration ~1-3s away"
            : "click 'start' to begin training"}
        </div>
      ) : (
        <>
          <Curve
            label="actor loss"
            samples={filteredSamples}
            field={(s) => s.actor_loss}
            color="var(--color-penumbra-cyan)"
            svgRef={svgRef}
            overlay={overlay}
          />
          <Curve
            label="critic loss"
            samples={filteredSamples}
            field={(s) => s.critic_loss}
            color="var(--color-penumbra-ember)"
          />
          <Curve
            label="entropy"
            samples={filteredSamples}
            field={(s) => s.entropy}
            color="color-mix(in srgb, var(--color-penumbra-cyan) 70%, white 20%)"
          />
          <Curve
            label="mean reward (rollout)"
            samples={filteredSamples}
            field={(s) => s.mean_reward}
            color="color-mix(in srgb, var(--color-penumbra-ember) 70%, white 20%)"
          />
          <BrushStatsCard
            range={range}
            stats={windowStats(filteredSamples.map((s) => s.mean_reward))}
            onClear={clear}
            startLabel={range ? `iter=${range.start}` : undefined}
            endLabel={range ? `iter=${range.end}` : undefined}
            countLabel="iters"
          />
        </>
      )}
    </div>
  );
}

interface CurveProps {
  label: string;
  samples: Sample[];
  field: (s: Sample) => number;
  color: string;
  width?: number;
  height?: number;
  svgRef?: React.RefObject<SVGSVGElement | null>;
  overlay?: React.ReactNode;
}

function Curve({
  label,
  samples,
  field,
  color,
  width = CURVE_W,
  height = CURVE_H,
  svgRef,
  overlay,
}: CurveProps) {
  if (samples.length === 0) {
    return (
      <div>
        <div className="mb-1 flex justify-between text-[10px]">
          <span className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
            {label}
          </span>
          <span className="tabular-nums text-[color:var(--color-penumbra-dim)]">∅</span>
        </div>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
          role="img"
          aria-label={label}
        >
          {overlay}
        </svg>
      </div>
    );
  }
  const values = samples.map(field);
  const vMin = Math.min(...values);
  const vMax = Math.max(...values);
  const span = vMax - vMin || 1;
  const sx = (i: number) => (i / Math.max(samples.length - 1, 1)) * (width - 60) + 50;
  const sy = (v: number) => height - ((v - vMin) / span) * (height - 10) - 4;
  const poly = samples.map((s, i) => `${sx(i)},${sy(field(s))}`).join(" ");
  const tail = values[values.length - 1] ?? 0;
  return (
    <div>
      <div className="mb-1 flex justify-between text-[10px]">
        <span className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          {label}
        </span>
        <span className="tabular-nums text-[color:var(--color-penumbra-text)]">
          {tail.toFixed(4)}
        </span>
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        role="img"
        aria-label={label}
      >
        <line
          x1={50}
          y1={height - 4}
          x2={width - 10}
          y2={height - 4}
          stroke="var(--color-penumbra-border)"
          strokeWidth={0.3}
        />
        <polyline points={poly} fill="none" stroke={color} strokeWidth={1.4} />
        {overlay}
      </svg>
    </div>
  );
}
