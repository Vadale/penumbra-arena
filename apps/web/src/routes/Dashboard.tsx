import { useState } from "react";
import { ChainExplorer } from "../chain/Explorer";
import { AnalyticsPanel } from "../charts/AnalyticsPanel";
import { CoachConsole } from "../coach/Console";
import { StatusBar } from "../shell/StatusBar";
import { usePenumbraStore } from "../streams/store";
import { usePenumbraSocket } from "../streams/ws";
import { ReplConsole } from "../terminal/ReplConsole";
import { Terminal } from "../terminal/Terminal";
import { Arena } from "../three/Arena";
import { Arena2D } from "../three/Arena2D";
import { TourOverlay } from "../tour/TourOverlay";

type BottomTab = "coach" | "terminal" | "repl";
type ArenaMode = "graph" | "3d";

export function Dashboard() {
  usePenumbraSocket();

  const connected = usePenumbraStore((s) => s.connected);
  const lastFrame = usePenumbraStore((s) => s.lastFrame);
  const [bottomTab, setBottomTab] = useState<BottomTab>("coach");
  const [arenaMode, setArenaMode] = useState<ArenaMode>("graph");

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] px-4 py-2">
        <div className="flex items-baseline gap-3">
          <div className="text-sm font-semibold tracking-tight text-[color:var(--color-penumbra-text)]">
            penumbra
          </div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-muted)]">
            privacy · perpetual · multi-agent
          </div>
        </div>
        <div className="flex items-center gap-3 text-[11px]">
          <span
            className={
              connected
                ? "rounded-sm border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]"
                : "rounded-sm border border-[color:var(--color-penumbra-ember)] bg-[color:var(--color-penumbra-ember-bg)] px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-ember)]"
            }
          >
            {connected ? "linked" : "offline"}
          </span>
        </div>
      </header>

      <main className="grid flex-1 grid-cols-[1fr_340px_300px] overflow-hidden">
        <section className="flex flex-col bg-[color:var(--color-penumbra-bg)]">
          <div className="relative flex-1 border-r border-[color:var(--color-penumbra-border)]">
            <div className="absolute right-3 top-3 z-10 flex gap-1 rounded-sm border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)]/90 px-2 py-1 text-[10px] uppercase tracking-wider">
              <ArenaTab active={arenaMode === "graph"} onClick={() => setArenaMode("graph")}>
                graph
              </ArenaTab>
              <span className="text-[color:var(--color-penumbra-border)]">·</span>
              <ArenaTab active={arenaMode === "3d"} onClick={() => setArenaMode("3d")}>
                3d
              </ArenaTab>
            </div>
            {arenaMode === "graph" ? <Arena2D /> : <Arena />}
          </div>
          <div className="flex max-h-[42%] flex-col border-t border-r border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)]">
            <div className="flex items-center gap-3 border-b border-[color:var(--color-penumbra-border)] px-3 py-1.5 text-[10px] uppercase tracking-[0.18em]">
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
            <div className="flex-1 overflow-y-auto p-3">
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

      <StatusBar lastFrame={lastFrame} connected={connected} />
      <TourOverlay />
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
    <div className="mb-2 border-b border-[color:var(--color-penumbra-border)] pb-1 text-[10px] uppercase tracking-[0.18em] text-[color:var(--color-penumbra-muted)]">
      {children}
    </div>
  );
}
