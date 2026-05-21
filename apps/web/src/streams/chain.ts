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

export function useChainLatest(): ChainLatest | null {
  const [latest, setLatest] = useState<ChainLatest | null>(null);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const response = await fetch("/chain/latest");
        if (!response.ok) return;
        const payload = (await response.json()) as ChainLatest;
        if (!cancelled) setLatest(payload);
      } catch {
        // network blip; the next poll will retry
      }
    };

    void poll();
    const timer = window.setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return latest;
}
