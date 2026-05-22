/**
 * Live reward-shaping sliders.
 *
 * Mutates the env's shared RewardWeights singleton. Next training
 * iteration (background trainer) picks up the new values; live
 * inference is unaffected (rewards only matter during training).
 */

import { useEffect, useState } from "react";

interface Weights {
  goal_reward: number;
  step_penalty: number;
  illegal_move_penalty: number;
  crowding_penalty: number;
}

const KEYS: (keyof Weights)[] = [
  "goal_reward",
  "step_penalty",
  "illegal_move_penalty",
  "crowding_penalty",
];

const RANGES: Record<keyof Weights, { min: number; max: number; step: number; help: string }> = {
  goal_reward: { min: 0, max: 5, step: 0.05, help: "reward when an agent reaches a goal" },
  step_penalty: { min: -0.2, max: 0, step: 0.005, help: "cost per tick — discourages dawdling" },
  illegal_move_penalty: {
    min: -1,
    max: 0,
    step: 0.05,
    help: "penalty for picking a non-existent neighbour",
  },
  crowding_penalty: {
    min: -0.5,
    max: 0,
    step: 0.01,
    help: "per-extra-agent penalty when N>1 agents share a node",
  },
};

export function RewardShapingChart() {
  const [data, setData] = useState<Weights | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const grab = async () => {
      try {
        const res = await fetch("/learning/reward-weights");
        if (!res.ok) return;
        const payload = (await res.json()) as Weights & { available?: boolean };
        if (!cancelled) setData(payload);
      } catch {}
    };
    void grab();
    const t = window.setInterval(grab, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  const update = async (key: keyof Weights, value: number) => {
    if (!data) return;
    const next = { ...data, [key]: value };
    setData(next);
    setPending(true);
    await fetch("/learning/reward-weights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [key]: value }),
    });
    setPending(false);
  };

  if (!data) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        loading reward weights…
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
        Mutate the reward components live. Background MAPPO training picks them up at the next
        iteration — start the trainer (from the "training" tile) and watch the policy adapt to the
        new objective.
      </div>
      {KEYS.map((key) => {
        const r = RANGES[key];
        return (
          <div key={key}>
            <div className="flex justify-between text-[10px]">
              <span className="uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
                {key}
              </span>
              <span className="tabular-nums text-[color:var(--color-penumbra-text)]">
                {data[key].toFixed(3)}
              </span>
            </div>
            <input
              type="range"
              min={r.min}
              max={r.max}
              step={r.step}
              value={data[key]}
              onChange={(e) => void update(key, Number(e.target.value))}
              disabled={pending}
              className="h-1 w-full accent-[color:var(--color-penumbra-cyan)]"
            />
            <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">{r.help}</div>
          </div>
        );
      })}
    </div>
  );
}
