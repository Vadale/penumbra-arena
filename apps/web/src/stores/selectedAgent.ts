/**
 * Selected-agent store.
 *
 * Concept taught: a single tiny zustand slice owns "which agent is the
 * user currently inspecting?" Any arena view (tilemap / world / graph /
 * 3D) sets it on click; the AgentDetailPanel reads it and fetches
 * `/agents/{id}`. Pulling this into its own store (instead of threading
 * a prop through Dashboard -> Arena views) keeps the click handlers
 * trivial and lets the panel mount once at the dashboard root.
 */

import { create } from "zustand";

interface SelectedAgentState {
  selectedAgentId: number | null;
  setSelectedAgentId: (id: number | null) => void;
}

export const useSelectedAgentStore = create<SelectedAgentState>((set) => ({
  selectedAgentId: null,
  setSelectedAgentId: (id) => set({ selectedAgentId: id }),
}));
