/**
 * Logistics — VRP optimization baseline tile.
 *
 * Shows the OR-style centralized planner solution (greedy + 2-opt) against
 * the system's actual fulfilment cost. The % gap is the headline metric:
 * how much could a perfectly-informed planner save vs the live policy?
 */

import { useState } from "react";
import { useFetchJsonPoll } from "../hooks/useFetchJson";
import { FetchError, Stat } from "./_shared";

interface RouteRow {
  agent_idx: number;
  n_stops: number;
  cost: number;
}

interface Payload {
  available: boolean;
  reason?: string;
  solver?: string;
  solver_total_cost?: number;
  actual_fulfilment_cost?: number;
  gap_fraction?: number;
  n_orders_served?: number;
  n_orders_unserved?: number;
  n_orders_considered?: number;
  compute_time_ms?: number;
  per_agent_routes?: RouteRow[];
}

export function LogisticsVRPChart() {
  const [solver, setSolver] = useState<"two_opt" | "greedy" | "or_tools">("two_opt");
  const state = useFetchJsonPoll<Payload>(`/logistics/vrp-baseline?solver=${solver}`, 10000);
  const data =
    state.kind === "data" ? state.value : state.kind === "error" ? state.lastValue : undefined;

  if (!data?.available) {
    return (
      <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)] space-y-2">
        {state.kind === "error" ? (
          <FetchError message={state.message} />
        ) : (
          <div>no VRP baseline yet ({data?.reason ?? "loading"})</div>
        )}
        <SolverPicker solver={solver} onChange={setSolver} />
      </div>
    );
  }

  const gap = data.gap_fraction ?? 0;
  const solverCost = data.solver_total_cost ?? 0;
  const actualCost = data.actual_fulfilment_cost ?? 0;
  const compute = data.compute_time_ms ?? 0;
  const routes = data.per_agent_routes ?? [];

  return (
    <div className="font-mono space-y-3">
      {state.kind === "error" && <FetchError message={state.message} />}
      <SolverPicker solver={solver} onChange={setSolver} />

      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="solver cost" value={solverCost} digits={2} />
        <Stat label="actual cost" value={actualCost} digits={2} />
        <Stat label="savings" value={gap * 100} digits={1} suffix="%" accent={gap > 0} />
      </div>

      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="served" value={data.n_orders_served ?? 0} />
        <Stat label="unserved" value={data.n_orders_unserved ?? 0} />
        <Stat label="solve ms" value={compute} digits={1} />
      </div>

      <div>
        <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)] mb-1">
          per-agent routes (top by cost) — solver: {data.solver}
        </div>
        <ul className="text-[10px] grid grid-cols-2 gap-x-3 gap-y-1">
          {routes
            .slice()
            .sort((a, b) => b.cost - a.cost)
            .slice(0, 12)
            .map((row) => (
              <li key={`vrp-route-${row.agent_idx}`}>
                ag#{row.agent_idx}: {row.n_stops} stops · cost {row.cost.toFixed(1)}
              </li>
            ))}
        </ul>
      </div>
    </div>
  );
}

interface PickerProps {
  solver: "two_opt" | "greedy" | "or_tools";
  onChange: (s: "two_opt" | "greedy" | "or_tools") => void;
}

function SolverPicker({ solver, onChange }: PickerProps) {
  const options: Array<{ value: PickerProps["solver"]; label: string }> = [
    { value: "greedy", label: "greedy" },
    { value: "two_opt", label: "2-opt" },
    { value: "or_tools", label: "or-tools" },
  ];
  return (
    <div className="flex gap-1 text-[10px]">
      {options.map((opt) => (
        <button
          type="button"
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-2 py-0.5 border ${
            solver === opt.value
              ? "border-[color:var(--color-penumbra-accent)] text-[color:var(--color-penumbra-accent)]"
              : "border-[color:var(--color-penumbra-border)] text-[color:var(--color-penumbra-muted)]"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
