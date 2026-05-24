/**
 * Lab-history store — keep the last N injection events this session.
 *
 * Concept taught: the Lab panel (and per-tile trigger buttons) all POST
 * to `/control/inject`; the UX nicety is "show me what I just fired".
 * Rather than scrolling a backend log we keep a tiny in-memory ring of
 * the last 20 successful POSTs. Pulling this into its own zustand slice
 * keeps the trigger components stateless and lets ANY consumer (DetailModal
 * confirmation line, LabPanel history list, future operator transcript)
 * read the same source of truth.
 */

import { create } from "zustand";

export type InjectionKind = "cpi.shock" | "garch.spike" | "agent.blocked" | "validator.slashed";

export interface InjectionRecord {
  kind: InjectionKind;
  tick: number;
  payload: Record<string, unknown>;
  at: number;
}

const MAX_HISTORY = 20;

interface LabHistoryState {
  history: InjectionRecord[];
  push: (entry: Omit<InjectionRecord, "at">) => void;
  clear: () => void;
}

export const useLabHistoryStore = create<LabHistoryState>((set) => ({
  history: [],
  push: (entry) =>
    set((s) => ({
      history: [{ ...entry, at: Date.now() }, ...s.history].slice(0, MAX_HISTORY),
    })),
  clear: () => set({ history: [] }),
}));
