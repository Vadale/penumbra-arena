/**
 * Arena topology client.
 *
 * Polls /arena/topology every 4s to keep the force-directed graph in
 * sync with the live arena (edge costs drift via OU; weather events
 * delete + re-add edges; goals migrate).
 */

import { useEffect, useState } from "react";

export interface TopologyEdge {
  u: number;
  v: number;
  cost: number;
}

export interface TopologySnapshot {
  nodes: number[];
  edges: TopologyEdge[];
  goals: number[];
  tick: number;
}

const POLL_MS = 4000;

export function useArenaTopology(): TopologySnapshot | null {
  const [snap, setSnap] = useState<TopologySnapshot | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch("/arena/topology");
        if (!res.ok) return;
        const payload = (await res.json()) as TopologySnapshot;
        if (!cancelled) setSnap(payload);
      } catch {
        // next poll will retry
      }
    };
    void poll();
    const timer = window.setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return snap;
}
