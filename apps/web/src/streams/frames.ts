/**
 * Wire-format types for messages streamed over the WebSocket.
 *
 * Concept taught: shape contracts. The server emits msgpack; the client
 * decodes into these plain-object types. Keep this file the single source
 * of truth for what's on the wire.
 */

export type MatchStatus = "running" | "won" | "expired";

export interface TickFrame {
  tick: number;
  match_id: number;
  match_status: MatchStatus;
  agent_positions: Record<number, number>;
  arena_edge_count: number;
  arena_goals: number[];
}

export function isTickFrame(value: unknown): value is TickFrame {
  if (typeof value !== "object" || value === null) return false;
  const frame = value as Record<string, unknown>;
  return (
    typeof frame.tick === "number" &&
    typeof frame.match_id === "number" &&
    typeof frame.match_status === "string" &&
    typeof frame.arena_edge_count === "number" &&
    Array.isArray(frame.arena_goals) &&
    typeof frame.agent_positions === "object"
  );
}
