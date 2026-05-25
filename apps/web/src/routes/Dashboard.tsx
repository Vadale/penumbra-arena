import { useCallback, useEffect, useMemo, useState } from "react";
import { ChainExplorer } from "../chain/Explorer";
import { NarrowViewportBanner } from "../charts/_shared";
import { AchievementToastHost } from "../charts/AchievementsPanel";
import { AgentDetailPanel } from "../charts/AgentDetailPanel";
import { AnalyticsPanel } from "../charts/AnalyticsPanel";
import {
  type NotificationPermissionState,
  permissionBadge,
  readPermission,
} from "../charts/NotificationSettings";
import { ReplayBanner, TimeScrubber } from "../charts/TimeScrubber";
import { WelcomeOverlay } from "../charts/WelcomeOverlay";
import { CoachConsole } from "../coach/Console";
import { useEventNotifications } from "../hooks/useEventNotifications";
import { HelpOverlay } from "../shell/HelpOverlay";
import { SpeedControl } from "../shell/SpeedControl";
import { StatusBar } from "../shell/StatusBar";
import { useKeyboardShortcuts } from "../shell/useKeyboardShortcuts";
import { useFrameHistoryRecorder } from "../streams/frameHistory";
import { usePenumbraStore } from "../streams/store";
import { usePenumbraSocket } from "../streams/ws";
import { ReplConsole } from "../terminal/ReplConsole";
import { Terminal } from "../terminal/Terminal";
import { Arena } from "../three/Arena";
import { Arena2D } from "../three/Arena2D";
import { TileMap } from "../three/TileMap";
import { WorldView } from "../three/WorldView";
import { TourOverlay } from "../tour/TourOverlay";

type BottomTab = "coach" | "terminal" | "repl";
type ArenaMode = "map" | "world" | "graph" | "3d";

// Persist the two view-mode selectors across page refreshes so a
// learner who picks "3d arena + shell tab" doesn't lose it on F5.
const BOTTOM_TAB_KEY = "penumbra.dashboard.bottomTab";
const ARENA_MODE_KEY = "penumbra.dashboard.arenaMode";
const BOTTOM_TABS: ReadonlySet<BottomTab> = new Set<BottomTab>(["coach", "terminal", "repl"]);
const ARENA_MODES: ReadonlySet<ArenaMode> = new Set<ArenaMode>(["map", "world", "graph", "3d"]);

function readStoredTab<T extends string>(key: string, allowed: ReadonlySet<T>, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw !== null && allowed.has(raw as T)) return raw as T;
  } catch {
    // localStorage throws in private-browsing — fall through to default.
  }
  return fallback;
}

function writeStoredTab(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // ignore quota / private-browsing failures
  }
}

export function Dashboard() {
  usePenumbraSocket();
  useFrameHistoryRecorder();
  useEventNotifications();

  const connected = usePenumbraStore((s) => s.connected);
  const lastFrame = usePenumbraStore((s) => s.lastFrame);
  const [bottomTab, setBottomTabState] = useState<BottomTab>(() =>
    readStoredTab<BottomTab>(BOTTOM_TAB_KEY, BOTTOM_TABS, "coach"),
  );
  const [arenaMode, setArenaModeState] = useState<ArenaMode>(() =>
    readStoredTab<ArenaMode>(ARENA_MODE_KEY, ARENA_MODES, "map"),
  );
  const setBottomTab = useCallback((next: BottomTab) => {
    setBottomTabState(next);
    writeStoredTab(BOTTOM_TAB_KEY, next);
  }, []);
  const setArenaMode = useCallback((next: ArenaMode) => {
    setArenaModeState(next);
    writeStoredTab(ARENA_MODE_KEY, next);
  }, []);
  const [helpOpen, setHelpOpen] = useState(false);
  const [paused, setPaused] = useState(false);
  const [timeWarp, setTimeWarp] = useState(1);
  // Mirrored from /control/tick_hz so the arena caption can show the
  // live rate without polling a second endpoint.
  const [tickHz, setTickHz] = useState<number | null>(null);
  const [notifPerm, setNotifPerm] = useState<NotificationPermissionState>(() => readPermission());

  useEffect(() => {
    const refresh = () => setNotifPerm(readPermission());
    refresh();
    window.addEventListener("focus", refresh);
    const handle = window.setInterval(refresh, 5000);
    return () => {
      window.removeEventListener("focus", refresh);
      window.clearInterval(handle);
    };
  }, []);

  const onPauseToggle = useCallback(async () => {
    const next = !paused;
    setPaused(next);
    try {
      await fetch(next ? "/control/pause" : "/control/resume", { method: "POST" });
    } catch {
      setPaused(!next); // revert on error
    }
  }, [paused]);

  const onTimeWarpDelta = useCallback(
    async (factor: number) => {
      const next = Math.max(1, Math.min(100, Math.round(timeWarp * factor)));
      if (next === timeWarp) return;
      setTimeWarp(next);
      try {
        await fetch(`/control/time-warp/${next}`, { method: "POST" });
      } catch {
        setTimeWarp(timeWarp);
      }
    },
    [timeWarp],
  );

  const shortcutHandlers = useMemo(
    () => ({
      onBottomTab: setBottomTab,
      onArenaToggle: () => {
        const next: ArenaMode =
          arenaMode === "map"
            ? "world"
            : arenaMode === "world"
              ? "graph"
              : arenaMode === "graph"
                ? "3d"
                : "map";
        setArenaMode(next);
      },
      onPauseToggle,
      onTimeWarpDelta,
      onHelpToggle: () => setHelpOpen((o) => !o),
    }),
    [arenaMode, setBottomTab, setArenaMode, onPauseToggle, onTimeWarpDelta],
  );

  useKeyboardShortcuts(shortcutHandlers);

  return (
    <div className="flex h-full flex-col">
      <NarrowViewportBanner />
      <header className="flex items-center justify-between border-b border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] px-4 py-2">
        <div className="flex items-baseline gap-3">
          <div className="text-sm font-semibold tracking-tight text-[color:var(--color-penumbra-text)]">
            penumbra
          </div>
          <div className="text-xs uppercase tracking-[0.2em] text-[color:var(--color-penumbra-muted)]">
            privacy · perpetual · multi-agent
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <SpeedControl paused={paused} onPauseToggle={onPauseToggle} onRateChange={setTickHz} />
          <a
            href="/bench"
            className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-xs uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            bench
          </a>
          <a
            href="/operator"
            className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-xs uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            operator
          </a>
          <a
            href="/config"
            className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-xs uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            config
          </a>
          <NotifPermBadge permission={notifPerm} />
          <ConnectionBadge connected={connected} lastFrame={lastFrame} />
        </div>
      </header>

      <main className="grid flex-1 grid-cols-[1fr_340px_300px] overflow-hidden">
        <section className="flex min-h-0 flex-col bg-[color:var(--color-penumbra-bg)]">
          <ArenaCaption tickHz={tickHz} />
          <div className="relative min-h-0 flex-1 border-r border-[color:var(--color-penumbra-border)]">
            <div className="absolute right-3 top-3 z-10 flex gap-1 rounded-sm border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)]/90 px-2 py-1 text-xs uppercase tracking-wider">
              <ArenaTab active={arenaMode === "map"} onClick={() => setArenaMode("map")}>
                map
              </ArenaTab>
              <span className="text-[color:var(--color-penumbra-border)]">·</span>
              <ArenaTab active={arenaMode === "world"} onClick={() => setArenaMode("world")}>
                world
              </ArenaTab>
              <span className="text-[color:var(--color-penumbra-border)]">·</span>
              <ArenaTab active={arenaMode === "graph"} onClick={() => setArenaMode("graph")}>
                graph
              </ArenaTab>
              <span className="text-[color:var(--color-penumbra-border)]">·</span>
              <ArenaTab active={arenaMode === "3d"} onClick={() => setArenaMode("3d")}>
                3d
              </ArenaTab>
            </div>
            {!connected && lastFrame === null && <ArenaEmptyState />}
            <ReplayBanner />
            {arenaMode === "map" && <TileMap />}
            {arenaMode === "world" && <WorldView />}
            {arenaMode === "graph" && <Arena2D />}
            {arenaMode === "3d" && <Arena />}
          </div>
          <TimeScrubber />
          <div className="flex h-[42%] min-h-0 flex-col border-t border-r border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)]">
            <div className="flex items-center gap-3 border-b border-[color:var(--color-penumbra-border)] px-3 py-1.5 text-xs uppercase tracking-[0.18em]">
              <PanelTab
                active={bottomTab === "coach"}
                onClick={() => setBottomTab("coach")}
                hint="curated pna/psh/pno chips — safe, in-process"
              >
                coach
              </PanelTab>
              <PanelTab
                active={bottomTab === "terminal"}
                onClick={() => setBottomTab("terminal")}
                hint="live macOS zsh PTY (requires PENUMBRA_ENABLE_PTY=1)"
              >
                shell
              </PanelTab>
              <PanelTab
                active={bottomTab === "repl"}
                onClick={() => setBottomTab("repl")}
                hint="sandboxed Python REPL with pna.api pre-imported"
              >
                repl
              </PanelTab>
            </div>
            {/* min-h-0 on the flex child is what lets xterm.js's */}
            {/* FitAddon read a real container height — without it the */}
            {/* terminal rows fall off the bottom of the panel. The */}
            {/* terminal owns its own scroll; the other tabs scroll */}
            {/* normally via overflow-y-auto. */}
            <div
              className={
                bottomTab === "terminal"
                  ? "min-h-0 flex-1 overflow-hidden p-3"
                  : "min-h-0 flex-1 overflow-y-auto p-3"
              }
            >
              {bottomTab === "coach" && <CoachConsole />}
              {bottomTab === "terminal" && <Terminal />}
              {bottomTab === "repl" && <ReplConsole />}
            </div>
          </div>
        </section>

        <aside className="overflow-y-auto border-r border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] p-3 text-xs">
          <SectionHeader>analytics</SectionHeader>
          <AnalyticsPanel />
        </aside>

        <aside className="overflow-y-auto bg-[color:var(--color-penumbra-panel)] p-3 text-xs">
          <SectionHeader>chain</SectionHeader>
          <ChainExplorer />
        </aside>
      </main>

      <StatusBar
        lastFrame={lastFrame}
        connected={connected}
        paused={paused}
        timeWarp={timeWarp}
        onHelp={() => setHelpOpen(true)}
      />
      <WelcomeOverlay />
      <TourOverlay />
      <HelpOverlay open={helpOpen} onClose={() => setHelpOpen(false)} />
      <AgentDetailPanel />
      <AchievementToastHost />
    </div>
  );
}

function ConnectionBadge({ connected, lastFrame }: { connected: boolean; lastFrame: unknown }) {
  // Three states a learner needs to be able to tell apart at a glance:
  //   linked  — WS open + at least one frame arrived (cyan)
  //   stale   — WS dropped but we still have a last frame to show. The
  //             arena is frozen, not dead; the user should know they
  //             are looking at the past (ember w/ "stale" word).
  //   offline — never connected (ember w/ "offline" word)
  if (connected) {
    return (
      <span
        role="status"
        aria-label="websocket linked, data is live"
        className="rounded-sm border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-1.5 py-0.5 text-xs uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]"
      >
        linked
      </span>
    );
  }
  const label = lastFrame !== null ? "stale" : "offline";
  const aria =
    lastFrame !== null
      ? "websocket dropped, showing last known frame"
      : "websocket offline, no data yet";
  return (
    <span
      role="status"
      aria-label={aria}
      title={aria}
      className="rounded-sm border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-1.5 py-0.5 text-xs uppercase tracking-wider text-[color:var(--color-penumbra-ember)]"
    >
      {label}
    </span>
  );
}

function NotifPermBadge({ permission }: { permission: NotificationPermissionState }) {
  const badge = permissionBadge(permission);
  return (
    <span
      role="status"
      aria-label={`notifications ${badge.label}`}
      title={`browser notifications ${badge.label}`}
      className={`rounded-sm border bg-[color:var(--color-penumbra-bg)] px-1.5 py-0.5 text-xs uppercase tracking-wider ${badge.className}`}
    >
      <span aria-hidden="true">{badge.symbol}</span> {badge.label}
    </span>
  );
}

function ArenaCaption({ tickHz }: { tickHz: number | null }) {
  return (
    <div className="border-b border-r border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] px-3 py-1 text-[11px] leading-snug text-[color:var(--color-penumbra-muted)]">
      50 agents (MAPPO-trained) on a dynamic graph &middot; positions encrypted (CKKS) &middot;
      matches end every ~60s &middot;{" "}
      <span className="text-[color:var(--color-penumbra-cyan)]">
        speed: {tickHz !== null ? `${tickHz} Hz` : "..."}
      </span>
    </div>
  );
}

function ArenaEmptyState() {
  return (
    <div className="pointer-events-none absolute inset-0 z-0 flex items-center justify-center bg-[color:var(--color-penumbra-bg)] text-xs text-[color:var(--color-penumbra-muted)]">
      Connecting to simulation... agents will appear once the first WS frame arrives.
    </div>
  );
}

function PanelTab({
  active,
  onClick,
  children,
  hint,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
  hint?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={hint}
      aria-label={hint ? `${children} — ${hint}` : children}
      className={
        active
          ? "border-b border-[color:var(--color-penumbra-cyan)] pb-0.5 text-[color:var(--color-penumbra-cyan)]"
          : "pb-0.5 text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-text)]"
      }
    >
      {children}
    </button>
  );
}

function ArenaTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "text-[color:var(--color-penumbra-cyan)]"
          : "text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-text)]"
      }
    >
      {children}
    </button>
  );
}

function SectionHeader({ children }: { children: string }) {
  return (
    <div className="mb-2 border-b border-[color:var(--color-penumbra-border)] pb-1 text-xs uppercase tracking-[0.18em] text-[color:var(--color-penumbra-muted)]">
      {children}
    </div>
  );
}
