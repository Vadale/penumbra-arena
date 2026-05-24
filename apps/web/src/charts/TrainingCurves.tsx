/**
 * Live MAPPO training curves: actor/critic loss + entropy + reward + KL.
 *
 * The same MAPPO actor that drives the live arena gets PPO updates
 * from a background trainer. Each iteration appends a row to the
 * curves; the dashboard re-renders so the user can watch the policy
 * mutate in real time. Start/stop with the button.
 */

import { useState } from "react";
import { useFetchJsonPoll } from "../hooks/useFetchJson";
import { FetchError, Stat } from "./_shared";

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

  if (!data?.available) {
    if (state.kind === "error") return <FetchError message={state.message} />;
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        live trainer unavailable (MAPPO checkpoint not loaded)
      </div>
    );
  }
  const samples = data.samples;
  const enabled = data.enabled ?? false;
  const iteration = data.iteration ?? 0;

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
            samples={samples}
            field={(s) => s.actor_loss}
            color="var(--color-penumbra-cyan)"
          />
          <Curve
            label="critic loss"
            samples={samples}
            field={(s) => s.critic_loss}
            color="var(--color-penumbra-ember)"
          />
          <Curve
            label="entropy"
            samples={samples}
            field={(s) => s.entropy}
            color="color-mix(in srgb, var(--color-penumbra-cyan) 70%, white 20%)"
          />
          <Curve
            label="mean reward (rollout)"
            samples={samples}
            field={(s) => s.mean_reward}
            color="color-mix(in srgb, var(--color-penumbra-ember) 70%, white 20%)"
          />
        </>
      )}
    </div>
  );
}

function Curve({
  label,
  samples,
  field,
  color,
  width = 560,
  height = 70,
}: {
  label: string;
  samples: Sample[];
  field: (s: Sample) => number;
  color: string;
  width?: number;
  height?: number;
}) {
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
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={label}>
        <line
          x1={50}
          y1={height - 4}
          x2={width - 10}
          y2={height - 4}
          stroke="var(--color-penumbra-border)"
          strokeWidth={0.3}
        />
        <polyline points={poly} fill="none" stroke={color} strokeWidth={1.4} />
      </svg>
    </div>
  );
}
