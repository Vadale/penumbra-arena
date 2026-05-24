/**
 * useEventNotifications — bridge backend EventBus to browser notifications.
 *
 * Concept taught: gating UI side effects on TWO consents. We poll
 * /events/recent every 5 seconds, diff against the last (tick, kind)
 * pair we've already surfaced, and for each genuinely-new event whose
 * kind is in the user's per-kind enabled set (localStorage), we fire
 * `new Notification(...)` IF the browser permission is granted. The
 * `tag` field collapses duplicates that a page reload might otherwise
 * re-show. Mount once from Dashboard.tsx — the hook is a no-op when
 * the API is unsupported or no kinds are enabled.
 */

import { useEffect, useRef } from "react";
import {
  NOTIFICATION_EVENT_KINDS,
  type NotificationEventKind,
  readEnabledKinds,
} from "../charts/NotificationSettings";

interface EventEntry {
  kind: string;
  tick: number;
  payload: Record<string, unknown>;
}

interface RecentPayload {
  events: EventEntry[];
}

const POLL_MS = 5000;
const KIND_SET: ReadonlySet<string> = new Set(NOTIFICATION_EVENT_KINDS);

function isKnownKind(kind: string): kind is NotificationEventKind {
  return KIND_SET.has(kind);
}

function describeEvent(e: EventEntry): { title: string; body: string } {
  const title = `Penumbra · ${e.kind}`;
  const payloadPreview =
    Object.keys(e.payload).length === 0 ? "" : JSON.stringify(e.payload).slice(0, 120);
  const body = payloadPreview ? `tick ${e.tick} · ${payloadPreview}` : `tick ${e.tick}`;
  return { title, body };
}

export function useEventNotifications(): void {
  // Tag of the most recent event we've already surfaced (or attempted
  // to surface). Compared by tick+kind so resetting the backend doesn't
  // race the local counter.
  const seenTagRef = useRef<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (typeof window.Notification === "undefined") return;

    let cancelled = false;
    let controller = new AbortController();

    const poll = async () => {
      const enabled = readEnabledKinds();
      // If the user has nothing enabled or hasn't granted permission,
      // skip the network call entirely — no work, no log noise.
      if (enabled.size === 0) return;
      if (window.Notification.permission !== "granted") return;

      controller = new AbortController();
      try {
        const res = await fetch("/events/recent?limit=20", { signal: controller.signal });
        if (!res.ok) return;
        const body = (await res.json()) as RecentPayload;
        const events = body.events ?? [];
        if (events.length === 0) return;
        const newest = events[events.length - 1];
        if (newest === undefined) return;
        const newestTag = `${newest.tick}:${newest.kind}`;
        const prevSeen = seenTagRef.current;
        // First poll seeds the cursor without firing — the user doesn't
        // want a flood of notifications for the backlog they just opened
        // the tab into.
        if (prevSeen === null) {
          seenTagRef.current = newestTag;
          return;
        }
        if (newestTag === prevSeen) return;

        // Find the index AFTER the previously-seen tag and surface only
        // the suffix. If we can't find it (e.g. the backend ring rolled
        // over), surface only the single newest event to bound noise.
        let startIdx = events.findIndex((e) => `${e.tick}:${e.kind}` === prevSeen);
        startIdx = startIdx >= 0 ? startIdx + 1 : events.length - 1;
        for (let i = startIdx; i < events.length; i++) {
          const ev = events[i];
          if (ev === undefined) continue;
          if (!isKnownKind(ev.kind)) continue;
          if (!enabled.has(ev.kind)) continue;
          const { title, body: notifBody } = describeEvent(ev);
          try {
            new window.Notification(title, {
              body: notifBody,
              tag: `${ev.tick}:${ev.kind}`,
            });
          } catch {
            // some browsers throw on Notification ctor when blurred;
            // swallow so polling continues
          }
        }
        seenTagRef.current = newestTag;
      } catch {
        // network error / abort — try again on the next interval
      }
    };

    void poll();
    const handle = window.setInterval(() => {
      if (!cancelled) void poll();
    }, POLL_MS);

    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(handle);
    };
  }, []);
}
