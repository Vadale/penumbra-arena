/**
 * Notification settings — opt-in browser notifications per event kind.
 *
 * Concept taught: the Web Notifications API is a permission-gated side
 * channel. Two layers of consent are involved: (1) the browser-level
 * Notification.permission grant, (2) the per-kind enable toggle the user
 * sets here. Both must agree before useEventNotifications fires a
 * notification. Preferences persist to localStorage so the choice
 * survives reloads; the permission state is read live from the
 * Notification API so the badge tracks reality even if the user changes
 * it from the browser address bar.
 */

import { useCallback, useEffect, useState } from "react";

const STORAGE_PREFIX = "penumbra.notifications.";

export const NOTIFICATION_EVENT_KINDS = [
  "cpi.shock",
  "garch.spike",
  "agent.blocked",
  "chain.block.finalised",
  "validator.slashed",
  "ml.policy.updated",
] as const;

export type NotificationEventKind = (typeof NOTIFICATION_EVENT_KINDS)[number];

const KIND_LABELS: Record<NotificationEventKind, string> = {
  "cpi.shock": "CPI shock",
  "garch.spike": "GARCH volatility spike",
  "agent.blocked": "agent blocked",
  "chain.block.finalised": "block finalised",
  "validator.slashed": "validator slashed",
  "ml.policy.updated": "policy updated",
};

function storageKey(kind: NotificationEventKind): string {
  return `${STORAGE_PREFIX}${kind}`;
}

export function readEnabledKinds(): Set<NotificationEventKind> {
  const enabled = new Set<NotificationEventKind>();
  if (typeof window === "undefined" || typeof window.localStorage === "undefined") return enabled;
  for (const kind of NOTIFICATION_EVENT_KINDS) {
    try {
      if (window.localStorage.getItem(storageKey(kind)) === "1") enabled.add(kind);
    } catch {
      // ignore quota / disabled
    }
  }
  return enabled;
}

function writeEnabledKind(kind: NotificationEventKind, on: boolean): void {
  if (typeof window === "undefined" || typeof window.localStorage === "undefined") return;
  try {
    if (on) window.localStorage.setItem(storageKey(kind), "1");
    else window.localStorage.removeItem(storageKey(kind));
  } catch {
    // ignore
  }
}

export type NotificationPermissionState = "granted" | "denied" | "default" | "unsupported";

export function readPermission(): NotificationPermissionState {
  if (typeof window === "undefined" || typeof window.Notification === "undefined") {
    return "unsupported";
  }
  return window.Notification.permission;
}

export function permissionBadge(state: NotificationPermissionState): {
  symbol: string;
  label: string;
  className: string;
} {
  if (state === "granted") {
    return {
      symbol: "✓",
      label: "active",
      className:
        "border-[color:var(--color-penumbra-cyan)] text-[color:var(--color-penumbra-cyan)]",
    };
  }
  if (state === "denied") {
    return {
      symbol: "×",
      label: "denied",
      className:
        "border-[color:var(--color-penumbra-ember)] text-[color:var(--color-penumbra-ember)]",
    };
  }
  if (state === "unsupported") {
    return {
      symbol: "—",
      label: "unsupported",
      className:
        "border-[color:var(--color-penumbra-border)] text-[color:var(--color-penumbra-dim)]",
    };
  }
  return {
    symbol: "○",
    label: "off",
    className:
      "border-[color:var(--color-penumbra-border)] text-[color:var(--color-penumbra-muted)]",
  };
}

export function NotificationSettings() {
  const [enabled, setEnabled] = useState<Set<NotificationEventKind>>(() => readEnabledKinds());
  const [permission, setPermission] = useState<NotificationPermissionState>(() => readPermission());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Listen for the optional permission-change event; not all browsers
    // implement it, so we also re-read on focus as a fallback.
    const refresh = () => setPermission(readPermission());
    window.addEventListener("focus", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
    };
  }, []);

  const toggle = useCallback((kind: NotificationEventKind) => {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) {
        next.delete(kind);
        writeEnabledKind(kind, false);
      } else {
        next.add(kind);
        writeEnabledKind(kind, true);
      }
      return next;
    });
  }, []);

  const requestPermission = useCallback(async () => {
    if (typeof window === "undefined" || typeof window.Notification === "undefined") return;
    setBusy(true);
    try {
      const result = await window.Notification.requestPermission();
      setPermission(result);
    } catch {
      // ignore — permission stays whatever it was
    } finally {
      setBusy(false);
    }
  }, []);

  const badge = permissionBadge(permission);

  return (
    <div className="font-mono space-y-3">
      <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
        Opt in to browser notifications when interesting cross-pillar events fire on the live
        backend. Preferences are stored locally; the browser permission is asked separately and can
        be revoked from the address bar.
      </div>

      <div className="flex items-center justify-between border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1.5">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
            browser permission
          </div>
          <div
            role="status"
            className={`inline-block border px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${badge.className}`}
            aria-label={`notification permission ${badge.label}`}
          >
            <span aria-hidden="true">{badge.symbol}</span> {badge.label}
          </div>
        </div>
        <button
          type="button"
          onClick={() => void requestPermission()}
          disabled={
            busy ||
            permission === "granted" ||
            permission === "denied" ||
            permission === "unsupported"
          }
          className="border border-[color:var(--color-penumbra-cyan)] px-2 py-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] hover:bg-[color:var(--color-penumbra-cyan-bg)] disabled:opacity-40"
        >
          {permission === "granted"
            ? "granted"
            : permission === "denied"
              ? "blocked in browser"
              : permission === "unsupported"
                ? "n/a"
                : busy
                  ? "asking…"
                  : "enable browser notifications"}
        </button>
      </div>

      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          event kinds
        </div>
        <ul className="space-y-1">
          {NOTIFICATION_EVENT_KINDS.map((kind) => {
            const on = enabled.has(kind);
            const inputId = `notif-${kind.replace(/\./g, "-")}`;
            return (
              <li
                key={kind}
                className="flex items-center justify-between border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1 text-[11px]"
              >
                <label htmlFor={inputId} className="flex items-center gap-2 cursor-pointer">
                  <input
                    id={inputId}
                    type="checkbox"
                    checked={on}
                    onChange={() => toggle(kind)}
                    aria-label={`notify on ${kind}`}
                  />
                  <span className="text-[color:var(--color-penumbra-text)]">
                    {KIND_LABELS[kind]}
                  </span>
                  <span className="text-[color:var(--color-penumbra-dim)]">({kind})</span>
                </label>
                <span
                  className={
                    on
                      ? "text-[color:var(--color-penumbra-cyan)] text-[10px] uppercase tracking-wider"
                      : "text-[color:var(--color-penumbra-dim)] text-[10px] uppercase tracking-wider"
                  }
                >
                  {on ? "on" : "off"}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="text-[9px] text-[color:var(--color-penumbra-dim)]">
        Notifications fire only when BOTH the per-kind toggle is on AND the browser permission is
        granted. The dashboard polls /events/recent every 5 seconds; duplicates are de-duplicated by
        Notification tag so a single event never produces two pop-ups.
      </div>
    </div>
  );
}
