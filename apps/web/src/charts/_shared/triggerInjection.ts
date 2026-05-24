/**
 * Shared inject-event POST helper used by the in-tile trigger buttons
 * (DetailModal) and the centralised LabPanel.
 *
 * Concept taught: factoring the call once means there is ONE place that
 * (a) constructs the JSON body, (b) parses the response, (c) records
 * the success in the labHistory store. Components only deal with their
 * own button/form state — pending, success, error.
 */

import {
  type InjectionKind,
  type InjectionRecord,
  useLabHistoryStore,
} from "../../stores/labHistory";

interface InjectResponse {
  ok: boolean;
  kind: InjectionKind;
  tick: number;
  payload: Record<string, unknown>;
}

export type InjectionResult =
  | { kind: "ok"; record: InjectionRecord }
  | { kind: "error"; message: string };

export async function triggerInjection(
  kind: InjectionKind,
  payload: Record<string, unknown>,
): Promise<InjectionResult> {
  let res: Response;
  try {
    res = await fetch("/control/inject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, payload }),
    });
  } catch (exc) {
    const msg = exc instanceof Error ? exc.message : String(exc);
    return { kind: "error", message: `network error: ${msg}` };
  }
  if (!res.ok) {
    return { kind: "error", message: `HTTP ${res.status} on /control/inject` };
  }
  let body: InjectResponse;
  try {
    body = (await res.json()) as InjectResponse;
  } catch {
    return { kind: "error", message: "invalid JSON from /control/inject" };
  }
  if (!body.ok) {
    return { kind: "error", message: `server rejected ${kind}` };
  }
  const record: InjectionRecord = {
    kind: body.kind,
    tick: body.tick,
    payload: body.payload,
    at: Date.now(),
  };
  useLabHistoryStore.getState().push({
    kind: record.kind,
    tick: record.tick,
    payload: record.payload,
  });
  return { kind: "ok", record };
}

interface StepResponse {
  previous_tick: number;
  new_tick: number;
  tick: number;
}

export type StepResult =
  | { kind: "ok"; previousTick: number; newTick: number }
  | { kind: "error"; message: string };

export async function stepSimulation(n: number): Promise<StepResult> {
  let res: Response;
  try {
    res = await fetch("/control/step", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ n }),
    });
  } catch (exc) {
    const msg = exc instanceof Error ? exc.message : String(exc);
    return { kind: "error", message: `network error: ${msg}` };
  }
  if (!res.ok) {
    return { kind: "error", message: `HTTP ${res.status} on /control/step` };
  }
  try {
    const body = (await res.json()) as StepResponse;
    return { kind: "ok", previousTick: body.previous_tick, newTick: body.new_tick };
  } catch {
    return { kind: "error", message: "invalid JSON from /control/step" };
  }
}
