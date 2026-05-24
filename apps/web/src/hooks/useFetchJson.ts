/**
 * Shared JSON-fetch hooks: useFetchJsonOnce + useFetchJsonPoll.
 *
 * Extracted from the ~60+ chart components that each re-implemented
 * `useEffect(() => { fetch + try/catch{} })`, silently swallowing
 * fetch errors and leaving tiles stuck in "warming…" with no signal
 * when the backend 500s. The hooks expose a discriminated-union state
 * the UI must handle exhaustively, and pair with the `FetchError`
 * component (`charts/_shared/FetchError.tsx`) for a uniform visual.
 *
 * Both variants:
 *   - HTTP non-2xx       → { kind: "error", message: "HTTP <status> on <url>" }
 *   - JSON parse failure → { kind: "error", message: "invalid JSON from <url>" }
 *   - Network throw      → { kind: "error", message: "network error: <msg>" }
 *   - Unmount            → AbortController cancels the in-flight request
 *
 * The polling variant keeps the last successful payload alongside an
 * error message so the UI can choose between "show stale + warning"
 * and "full error".
 */

import { useEffect, useRef, useState } from "react";

export type FetchState<T> =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "data"; value: T }
  | { kind: "error"; message: string };

export type PollFetchState<T> =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "data"; value: T }
  | { kind: "error"; message: string; lastValue?: T };

export interface UseFetchJsonOptions {
  enabled?: boolean;
}

interface AbortLike {
  name?: string;
}

function isAbortError(exc: unknown): boolean {
  if (exc instanceof DOMException && exc.name === "AbortError") return true;
  if (typeof exc === "object" && exc !== null && "name" in exc) {
    return (exc as AbortLike).name === "AbortError";
  }
  return false;
}

function errorMessage(exc: unknown): string {
  if (exc instanceof Error) return exc.message;
  return String(exc);
}

async function fetchJsonInner<T>(url: string, signal: AbortSignal): Promise<FetchState<T>> {
  let res: Response;
  try {
    res = await fetch(url, { signal });
  } catch (exc) {
    if (isAbortError(exc)) return { kind: "loading" };
    return { kind: "error", message: `network error: ${errorMessage(exc)}` };
  }
  if (!res.ok) {
    return { kind: "error", message: `HTTP ${res.status} on ${url}` };
  }
  try {
    const value = (await res.json()) as T;
    return { kind: "data", value };
  } catch (exc) {
    if (isAbortError(exc)) return { kind: "loading" };
    return { kind: "error", message: `invalid JSON from ${url}` };
  }
}

export function useFetchJsonOnce<T>(url: string, opts?: UseFetchJsonOptions): FetchState<T> {
  const enabled = opts?.enabled ?? true;
  const [state, setState] = useState<FetchState<T>>(
    enabled ? { kind: "loading" } : { kind: "idle" },
  );

  useEffect(() => {
    if (!enabled) {
      setState({ kind: "idle" });
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    setState({ kind: "loading" });
    void fetchJsonInner<T>(url, controller.signal).then((next) => {
      if (cancelled) return;
      if (next.kind === "loading") return;
      setState(next);
    });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [url, enabled]);

  return state;
}

export function useFetchJsonPoll<T>(
  url: string,
  intervalMs: number,
  opts?: UseFetchJsonOptions,
): PollFetchState<T> {
  const enabled = opts?.enabled ?? true;
  const [state, setState] = useState<PollFetchState<T>>(
    enabled ? { kind: "loading" } : { kind: "idle" },
  );
  const lastValueRef = useRef<T | undefined>(undefined);

  useEffect(() => {
    if (!enabled) {
      setState({ kind: "idle" });
      lastValueRef.current = undefined;
      return;
    }
    let cancelled = false;
    let controller = new AbortController();
    setState({ kind: "loading" });

    const tick = async () => {
      controller = new AbortController();
      const next = await fetchJsonInner<T>(url, controller.signal);
      if (cancelled) return;
      if (next.kind === "data") {
        lastValueRef.current = next.value;
        setState(next);
        return;
      }
      if (next.kind === "error") {
        const stale = lastValueRef.current;
        setState(
          stale !== undefined
            ? { kind: "error", message: next.message, lastValue: stale }
            : { kind: "error", message: next.message },
        );
      }
    };

    void tick();
    const handle = window.setInterval(() => void tick(), intervalMs);
    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(handle);
    };
  }, [url, intervalMs, enabled]);

  return state;
}
