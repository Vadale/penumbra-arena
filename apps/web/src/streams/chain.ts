/**
 * Chain explorer client: polls /chain/latest periodically and exposes
 * a small zustand-style hook for the panel.
 */

import { useEffect, useState } from "react";

export interface BlockOutcomeView {
  match_id: number;
  winner_agent_id: number | null;
  end_tick: number;
  end_reason: string;
}

export interface BlockSlashingView {
  offender_pubkey: string;
  height_observed: number;
}

export interface BlockView {
  hash: string;
  height: number;
  prev_hash: string;
  merkle_root: string;
  proposer_pubkey: string;
  timestamp_ns: number;
  outcomes: BlockOutcomeView[];
  slashings: BlockSlashingView[];
  validator_count: number;
}

export interface ChainLatest {
  height: number;
  head_hash?: string;
  blocks: BlockView[];
}

const POLL_MS = 3_000;

export interface ChainLatestQuery {
  latest: ChainLatest | null;
  /**
   * Set when the last poll failed AND we have no previous snapshot to
   * show. Lets the Chain Explorer render "couldn't reach /chain" instead
   * of looping a connecting spinner forever when the backend is down.
   */
  error: string | null;
}

export function useChainLatest(): ChainLatestQuery {
  const [latest, setLatest] = useState<ChainLatest | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let currentController: AbortController | null = null;

    const poll = async () => {
      // Abort the previous request before the next one fires so a slow
      // backend can't queue concurrent fetches behind the 3 s interval.
      currentController?.abort();
      const controller = new AbortController();
      currentController = controller;
      try {
        const response = await fetch("/chain/latest", { signal: controller.signal });
        if (cancelled || controller.signal.aborted) return;
        if (!response.ok) {
          setError(`HTTP ${response.status} from /chain/latest`);
          return;
        }
        const payload = (await response.json()) as ChainLatest;
        if (cancelled || controller.signal.aborted) return;
        setError(null);
        setLatest(payload);
      } catch (exc) {
        if (cancelled || controller.signal.aborted) return;
        if (exc instanceof DOMException && exc.name === "AbortError") return;
        setError(exc instanceof Error ? exc.message : "fetch /chain/latest failed");
      }
    };

    void poll();
    const timer = window.setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      currentController?.abort();
      window.clearInterval(timer);
    };
  }, []);

  return { latest, error };
}
