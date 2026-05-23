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
 *
 * Phase 6a Tier 4 also adds a live per-agent carrier-rewards
 * sparkline (top 5 earners over the rolling 200-fulfilment window),
 * polled from /learning/carrier-reward-stream at 5s.
 */

import { useEffect, useMemo, useState } from "react";

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

interface CarrierRewardEntry {
  agent_id: number;
  reward: number;
  tick: number;
}

interface CarrierRewardStream {
  available: boolean;
  rewards: CarrierRewardEntry[];
  per_agent: { agent_id: number; total_reward: number; count: number }[];
  total_carrier_fulfilments: number;
  last_fulfilment_tick: number;
}

export function RewardShapingChart() {
  const [data, setData] = useState<Weights | null>(null);
  const [pending, setPending] = useState(false);
  const [stream, setStream] = useState<CarrierRewardStream | null>(null);

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

  useEffect(() => {
    let cancelled = false;
    const pullStream = async () => {
      try {
        const res = await fetch("/learning/carrier-reward-stream?limit=200");
        if (!res.ok) return;
        const payload = (await res.json()) as CarrierRewardStream;
        if (!cancelled) setStream(payload);
      } catch {}
    };
    void pullStream();
    const t = window.setInterval(pullStream, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  const top5 = useMemo(() => {
    if (!stream?.per_agent) return [];
    return stream.per_agent.slice(0, 5);
  }, [stream]);

  const sparklines = useMemo(() => {
    if (!stream?.rewards) return new Map<number, number[]>();
    const map = new Map<number, number[]>();
    for (const entry of stream.rewards) {
      const arr = map.get(entry.agent_id) ?? [];
      arr.push(entry.reward);
      map.set(entry.agent_id, arr);
    }
    return map;
  }, [stream]);

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
      <CarrierRewardsSparkline top5={top5} sparklines={sparklines} stream={stream} />
    </div>
  );
}

function CarrierRewardsSparkline({
  top5,
  sparklines,
  stream,
}: {
  top5: { agent_id: number; total_reward: number; count: number }[];
  sparklines: Map<number, number[]>;
  stream: CarrierRewardStream | null;
}) {
  if (stream === null) {
    return (
      <div className="border-t border-[color:var(--color-penumbra-line)] pt-2 text-[10px] text-[color:var(--color-penumbra-muted)]">
        loading carrier-rewards stream…
      </div>
    );
  }
  if (!stream.available || top5.length === 0) {
    return (
      <div className="border-t border-[color:var(--color-penumbra-line)] pt-2 text-[10px] text-[color:var(--color-penumbra-dim)]">
        no carrier rewards recorded yet (need orders to be fulfilled by real agents)
      </div>
    );
  }
  const max = Math.max(1, ...Array.from(sparklines.values()).flatMap((series) => series));
  return (
    <div className="border-t border-[color:var(--color-penumbra-line)] pt-2 space-y-1">
      <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]">
        top 5 carriers (last {stream.rewards.length} fulfilments, {stream.total_carrier_fulfilments}{" "}
        total)
      </div>
      {top5.map((row) => {
        const series = sparklines.get(row.agent_id) ?? [];
        return (
          <div key={row.agent_id} className="flex items-center gap-2 text-[10px]">
            <span className="w-14 text-[color:var(--color-penumbra-muted)]">
              agent {row.agent_id}
            </span>
            <Sparkline series={series} max={max} />
            <span className="w-16 text-right tabular-nums text-[color:var(--color-penumbra-text)]">
              {row.total_reward.toFixed(2)}
            </span>
            <span className="w-8 text-right tabular-nums text-[color:var(--color-penumbra-dim)]">
              ×{row.count}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function Sparkline({ series, max }: { series: number[]; max: number }) {
  if (series.length === 0) return <span className="flex-1" />;
  const width = 100;
  const height = 16;
  const step = series.length > 1 ? width / (series.length - 1) : width;
  const points = series
    .map(
      (value, idx) => `${(idx * step).toFixed(1)},${(height - (value / max) * height).toFixed(1)}`,
    )
    .join(" ");
  return (
    <svg width={width} height={height} className="flex-1" aria-hidden="true">
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth={1}
        points={points}
        className="text-[color:var(--color-penumbra-cyan)]"
      />
    </svg>
  );
}
