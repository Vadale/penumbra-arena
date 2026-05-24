/**
 * Logistics fill-rate tile.
 *
 * Surfaces the end-customer demand satisfaction ratio (served /
 * requested) and the per-product breakdown. Polled every 5s.
 */

import { useFetchJsonPoll } from "../hooks/useFetchJson";
import { FetchError, Stat } from "./_shared";

interface Payload {
  available: boolean;
  overall_fill_rate?: number;
  total_served?: number;
  total_requested?: number;
  total_backlog?: number;
  per_product?: Array<[number, number]>;
}

export function LogisticsFillRateChart() {
  const state = useFetchJsonPoll<Payload>("/logistics/fill-rate", 5000);
  const data =
    state.kind === "data" ? state.value : state.kind === "error" ? state.lastValue : undefined;

  if (!data?.available) {
    if (state.kind === "error") return <FetchError message={state.message} />;
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
        no demand data yet
      </div>
    );
  }
  const rate = data.overall_fill_rate ?? 0;
  const isGood = rate >= 0.9;
  return (
    <div className="font-mono space-y-3">
      {state.kind === "error" && <FetchError message={state.message} />}
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat
          label="fill rate"
          value={rate * 100}
          accent={isGood}
          ember={!isGood}
          digits={1}
          suffix="%"
        />
        <Stat label="served" value={data.total_served ?? 0} />
        <Stat
          label="backlog"
          value={data.total_backlog ?? 0}
          ember={(data.total_backlog ?? 0) > 0}
        />
      </div>
      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        served / requested across all (city, product) pairs. Backlog accumulates when demand outruns
        inventory.
      </div>
    </div>
  );
}
