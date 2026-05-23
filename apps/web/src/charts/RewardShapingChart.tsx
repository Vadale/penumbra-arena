/**
 * Live reward-shaping sliders.
 *
 * Mutates the env's shared RewardWeights singleton. Next training
 * iteration (background trainer) picks up the new values; live
 * inference is unaffected (rewards only matter during training).
 *
 * Tier 4 (logistics) adds three additional sliders that wire the
 * supply-chain KPIs into the MAPPO reward:
 *   - logistics_dispatch_bonus: per fulfilled order assigned to a carrier
 *   - logistics_dispatch_penalty: per-tick cost for stale assignments
 *   - fill_rate_bonus: scaled by overall fill rate at episode end
 */

import { useEffect, useState } from "react";

interface Weights {
  goal_reward: number;
  step_penalty: number;
  illegal_move_penalty: number;
  crowding_penalty: number;
  logistics_dispatch_bonus: number;
  logistics_dispatch_penalty: number;
  fill_rate_bonus: number;
}

const KEYS: (keyof Weights)[] = [
  "goal_reward",
  "step_penalty",
  "illegal_move_penalty",
  "crowding_penalty",
  "logistics_dispatch_bonus",
  "logistics_dispatch_penalty",
  "fill_rate_bonus",
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
  logistics_dispatch_bonus: {
    min: 0,
    max: 5,
    step: 0.05,
    help: "reward for a carrier that fulfils an order (logistics)",
  },
  logistics_dispatch_penalty: {
    min: 0,
    max: 1,
    step: 0.01,
    help: "per-tick cost for a carrier holding a stale assignment (logistics)",
  },
  fill_rate_bonus: {
    min: 0,
    max: 20,
    step: 0.1,
    help: "episode-end shared bonus scaled by overall fill rate (logistics)",
  },
};

const LOGISTICS_KEYS = new Set<keyof Weights>([
  "logistics_dispatch_bonus",
  "logistics_dispatch_penalty",
  "fill_rate_bonus",
]);

const LOGISTICS_PAYLOAD_KEYS: Partial<Record<keyof Weights, string>> = {
  logistics_dispatch_bonus: "dispatch_bonus",
  logistics_dispatch_penalty: "dispatch_penalty",
  fill_rate_bonus: "fill_rate_bonus",
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
    if (LOGISTICS_KEYS.has(key)) {
      const payloadKey = LOGISTICS_PAYLOAD_KEYS[key] ?? key;
      await fetch("/learning/reward-weights/logistics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [payloadKey]: value }),
      });
    } else {
      await fetch("/learning/reward-weights", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: value }),
      });
    }
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
        new objective. Logistics rows (default 0) make carriers logistics-aware when nonzero.
      </div>
      {KEYS.map((key) => {
        const r = RANGES[key];
        const isLogistics = LOGISTICS_KEYS.has(key);
        return (
          <div key={key}>
            <div className="flex justify-between text-[10px]">
              <span
                className={`uppercase tracking-wider ${
                  isLogistics
                    ? "text-[color:var(--color-penumbra-cyan)]"
                    : "text-[color:var(--color-penumbra-muted)]"
                }`}
              >
                {key}
              </span>
              <span className="tabular-nums text-[color:var(--color-penumbra-text)]">
                {(data[key] ?? 0).toFixed(3)}
              </span>
            </div>
            <input
              type="range"
              min={r.min}
              max={r.max}
              step={r.step}
              value={data[key] ?? 0}
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
