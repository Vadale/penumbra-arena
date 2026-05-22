/**
 * Live MAPPO inspection + control client.
 *
 * Polls `/learning/action-histogram` for the swarm-wide action mix
 * and exposes one-shot fetches for per-agent policy inspection +
 * mutators for temperature / enabled.
 */

import { useEffect, useState } from "react";

export interface PolicyInspection {
  available: boolean;
  agent_id?: number;
  current_node?: number;
  observation?: number[];
  neighbour_nodes?: number[];
  action_labels?: string[];
  action_probabilities?: number[];
  chosen_action?: number;
  temperature?: number;
  deterministic?: boolean;
  enabled?: boolean;
  reason?: string;
}

export interface ActionHistogramRow {
  action: string;
  count: number;
}

export interface ActionHistogram {
  available: boolean;
  histogram: ActionHistogramRow[];
  n_agents?: number;
  temperature?: number;
  enabled?: boolean;
}

export interface MappoRuntimeState {
  available: boolean;
  temperature?: number;
  deterministic?: boolean;
  enabled?: boolean;
}

export async function fetchPolicy(agentId: number): Promise<PolicyInspection | null> {
  try {
    const res = await fetch(`/learning/policy/${agentId}`);
    if (!res.ok) return null;
    return (await res.json()) as PolicyInspection;
  } catch {
    return null;
  }
}

export async function fetchRuntime(): Promise<MappoRuntimeState | null> {
  try {
    const res = await fetch("/learning/runtime");
    if (!res.ok) return null;
    return (await res.json()) as MappoRuntimeState;
  } catch {
    return null;
  }
}

export async function setTemperature(value: number): Promise<void> {
  await fetch(`/learning/temperature/${value}`, { method: "POST" });
}

export async function setEnabled(enabled: boolean): Promise<void> {
  await fetch(`/learning/enabled/${enabled}`, { method: "POST" });
}

const POLL_MS = 1000;

export function useActionHistogram(): ActionHistogram | null {
  const [data, setData] = useState<ActionHistogram | null>(null);
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch("/learning/action-histogram");
        if (!res.ok) return;
        const payload = (await res.json()) as ActionHistogram;
        if (!cancelled) setData(payload);
      } catch {
        // next poll retries
      }
    };
    void poll();
    const timer = window.setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);
  return data;
}
