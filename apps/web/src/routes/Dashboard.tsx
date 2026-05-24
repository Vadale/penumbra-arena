import { useCallback, useMemo, useState } from "react";
import { ChainExplorer } from "../chain/Explorer";
import { NarrowViewportBanner } from "../charts/_shared";
import { AnalyticsPanel } from "../charts/AnalyticsPanel";
import { WelcomeOverlay } from "../charts/WelcomeOverlay";
import { CoachConsole } from "../coach/Console";
import { HelpOverlay } from "../shell/HelpOverlay";
import { SpeedControl } from "../shell/SpeedControl";
import { StatusBar } from "../shell/StatusBar";
import { useKeyboardShortcuts } from "../shell/useKeyboardShortcuts";
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

export function Dashboard() {
  usePenumbraSocket();

  const connected = usePenumbraStore((s) => s.connected);
  const lastFrame = usePenumbraStore((s) => s.lastFrame);
  const [bottomTab, setBottomTab] = useState<BottomTab>("coach");
  const [arenaMode, setArenaMode] = useState<ArenaMode>("map");
  const [helpOpen, setHelpOpen] = useState(false);
  const [paused, setPaused] = useState(false);
  const [timeWarp, setTimeWarp] = useState(1);
  // Mirrored from /control/tick_hz so the arena caption can show the
  // live rate without polling a second endpoint.
  const [tickHz, setTickHz] = useState<number | null>(null);

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
      onArenaToggle: () =>
        setArenaMode((m) =>
          m === "map" ? "world" : m === "world" ? "graph" : m === "graph" ? "3d" : "map",
        ),
      onPauseToggle,
      onTimeWarpDelta,
      onHelpToggle: () => setHelpOpen((o) => !o),
    }),
    [onPauseToggle, onTimeWarpDelta],
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
          <span
            className={
              connected
                ? "rounded-sm border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-1.5 py-0.5 text-xs uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]"
                : "rounded-sm border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-1.5 py-0.5 text-xs uppercase tracking-wider text-[color:var(--color-penumbra-ember)]"
            }
          >
            {connected ? "linked" : "offline"}
          </span>
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
            {arenaMode === "map" && <TileMap />}
            {arenaMode === "world" && <WorldView />}
            {arenaMode === "graph" && <Arena2D />}
            {arenaMode === "3d" && <Arena />}
          </div>
          <div className="flex h-[42%] min-h-0 flex-col border-t border-r border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)]">
            <div className="flex items-center gap-3 border-b border-[color:var(--color-penumbra-border)] px-3 py-1.5 text-xs uppercase tracking-[0.18em]">
              <PanelTab active={bottomTab === "coach"} onClick={() => setBottomTab("coach")}>
                coach
              </PanelTab>
              <PanelTab active={bottomTab === "terminal"} onClick={() => setBottomTab("terminal")}>
                shell
              </PanelTab>
              <PanelTab active={bottomTab === "repl"} onClick={() => setBottomTab("repl")}>
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
    </div>
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
