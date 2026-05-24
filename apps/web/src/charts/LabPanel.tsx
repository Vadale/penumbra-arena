/**
 * Lab — centralised one-stop for live experiment injection.
 *
 * Concept taught: a dashboard-grade SUT (system under test) is only
 * useful if you can perturb it on demand. This panel exposes the four
 * Wave-1A inject kinds (CPI shock, GARCH spike, agent block, validator
 * slash) plus a manual stepper as a single keyboard-discoverable
 * surface so a learner can "do an experiment" without leaving the
 * dashboard. Recent injections (this session) read from the
 * labHistoryStore so any tile-level trigger also lands here.
 */

import { useState } from "react";
import { useAchievementsStore } from "../stores/achievements";
import { useLabHistoryStore } from "../stores/labHistory";
import { stepSimulation, triggerInjection } from "./_shared/triggerInjection";

interface FireState {
  pending: boolean;
  confirmation: string | null;
  error: string | null;
}

const IDLE: FireState = { pending: false, confirmation: null, error: null };

function useFireState() {
  const [state, setState] = useState<FireState>(IDLE);
  return {
    state,
    start: () => setState({ pending: true, confirmation: null, error: null }),
    ok: (msg: string) => setState({ pending: false, confirmation: msg, error: null }),
    fail: (msg: string) => setState({ pending: false, confirmation: null, error: msg }),
  };
}

function Row({
  label,
  control,
  state,
}: {
  label: string;
  control: React.ReactNode;
  state: FireState;
}) {
  return (
    <div className="flex flex-col gap-1 border-b border-[color:var(--color-penumbra-border)] py-1 last:border-b-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-32 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)]">
          {label}
        </span>
        {control}
      </div>
      {state.confirmation && (
        <div className="font-mono text-[10px] text-[color:var(--color-penumbra-cyan)]">
          {state.confirmation}
        </div>
      )}
      {state.error && (
        <div className="font-mono text-[10px] text-[color:var(--color-penumbra-ember)]">
          {state.error}
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-dim)]">
        == {title} ==
      </div>
      <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
        {children}
      </div>
    </div>
  );
}

export function LabPanel() {
  const history = useLabHistoryStore((s) => s.history);
  const incrementLabTriggers = useAchievementsStore((s) => s.incrementLabTriggers);

  const cpi = useFireState();
  const [cpiRatio, setCpiRatio] = useState<number>(1.5);
  const garch = useFireState();
  const [garchMag, setGarchMag] = useState<number>(3.0);
  const block = useFireState();
  const [blockAgentId, setBlockAgentId] = useState<number>(0);
  const [blockReason, setBlockReason] = useState<string>("lab experiment");
  const slash = useFireState();
  const [slashId, setSlashId] = useState<number>(0);

  const step = useFireState();

  const fireCpi = async () => {
    cpi.start();
    const r = await triggerInjection("cpi.shock", { ratio: cpiRatio });
    if (r.kind === "ok") {
      cpi.ok(`✓ cpi.shock fired at tick ${r.record.tick}`);
      incrementLabTriggers();
    } else cpi.fail(r.message);
  };
  const fireGarch = async () => {
    garch.start();
    const r = await triggerInjection("garch.spike", { magnitude: garchMag });
    if (r.kind === "ok") {
      garch.ok(`✓ garch.spike fired at tick ${r.record.tick}`);
      incrementLabTriggers();
    } else garch.fail(r.message);
  };
  const fireBlock = async () => {
    block.start();
    const r = await triggerInjection("agent.blocked", {
      agent_id: blockAgentId,
      reason: blockReason,
    });
    if (r.kind === "ok") {
      block.ok(`✓ agent.blocked fired at tick ${r.record.tick}`);
      incrementLabTriggers();
    } else block.fail(r.message);
  };
  const fireSlash = async () => {
    slash.start();
    const r = await triggerInjection("validator.slashed", { validator_id: slashId });
    if (r.kind === "ok") {
      slash.ok(`✓ validator.slashed fired at tick ${r.record.tick}`);
      incrementLabTriggers();
    } else slash.fail(r.message);
  };

  const fireStep = async (n: number) => {
    step.start();
    const r = await stepSimulation(n);
    if (r.kind === "ok") step.ok(`✓ stepped ${n} (tick ${r.previousTick} → ${r.newTick})`);
    else step.fail(r.message);
  };

  const fireBtnClass =
    "border border-[color:var(--color-penumbra-cyan)] bg-transparent px-2 py-[2px] font-mono text-[11px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)] hover:bg-[color:var(--color-penumbra-cyan)] hover:text-[color:var(--color-penumbra-bg)] disabled:opacity-50";
  const inputClass =
    "w-16 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 py-[1px] font-mono text-[10px] text-[color:var(--color-penumbra-text)]";

  return (
    <div className="space-y-3 font-mono">
      <Section title="inject events">
        <Row
          label="cpi shock"
          state={cpi.state}
          control={
            <>
              <button
                type="button"
                onClick={() => void fireCpi()}
                disabled={cpi.state.pending}
                className={fireBtnClass}
              >
                {cpi.state.pending ? "firing…" : "trigger cpi shock"}
              </button>
              <label className="text-[10px] text-[color:var(--color-penumbra-muted)]">
                ratio{" "}
                <input
                  type="number"
                  step="0.1"
                  value={cpiRatio}
                  onChange={(e) => setCpiRatio(Number.parseFloat(e.target.value) || 0)}
                  className={inputClass}
                  aria-label="cpi shock ratio"
                />
              </label>
            </>
          }
        />
        <Row
          label="garch spike"
          state={garch.state}
          control={
            <>
              <button
                type="button"
                onClick={() => void fireGarch()}
                disabled={garch.state.pending}
                className={fireBtnClass}
              >
                {garch.state.pending ? "firing…" : "force garch spike"}
              </button>
              <label className="text-[10px] text-[color:var(--color-penumbra-muted)]">
                magnitude{" "}
                <input
                  type="number"
                  step="0.1"
                  value={garchMag}
                  onChange={(e) => setGarchMag(Number.parseFloat(e.target.value) || 0)}
                  className={inputClass}
                  aria-label="garch spike magnitude"
                />
              </label>
            </>
          }
        />
        <Row
          label="block agent"
          state={block.state}
          control={
            <>
              <button
                type="button"
                onClick={() => void fireBlock()}
                disabled={block.state.pending}
                className={fireBtnClass}
              >
                {block.state.pending ? "firing…" : "block agent #"}
              </button>
              <label className="text-[10px] text-[color:var(--color-penumbra-muted)]">
                id{" "}
                <input
                  type="number"
                  min={0}
                  value={blockAgentId}
                  onChange={(e) => setBlockAgentId(Number.parseInt(e.target.value, 10) || 0)}
                  className={inputClass}
                  aria-label="block agent id"
                />
              </label>
              <label className="text-[10px] text-[color:var(--color-penumbra-muted)]">
                reason{" "}
                <input
                  type="text"
                  value={blockReason}
                  onChange={(e) => setBlockReason(e.target.value)}
                  className="w-32 border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 py-[1px] font-mono text-[10px] text-[color:var(--color-penumbra-text)]"
                  aria-label="block agent reason"
                />
              </label>
            </>
          }
        />
        <Row
          label="slash validator"
          state={slash.state}
          control={
            <>
              <button
                type="button"
                onClick={() => void fireSlash()}
                disabled={slash.state.pending}
                className={fireBtnClass}
              >
                {slash.state.pending ? "firing…" : "slash validator #"}
              </button>
              <label className="text-[10px] text-[color:var(--color-penumbra-muted)]">
                id{" "}
                <input
                  type="number"
                  min={0}
                  value={slashId}
                  onChange={(e) => setSlashId(Number.parseInt(e.target.value, 10) || 0)}
                  className={inputClass}
                  aria-label="slash validator id"
                />
              </label>
            </>
          }
        />
      </Section>

      <Section title="step the simulation">
        <Row
          label="manual step"
          state={step.state}
          control={
            <>
              <button
                type="button"
                onClick={() => void fireStep(1)}
                disabled={step.state.pending}
                className={fireBtnClass}
              >
                step 1
              </button>
              <button
                type="button"
                onClick={() => void fireStep(10)}
                disabled={step.state.pending}
                className={fireBtnClass}
              >
                step 10
              </button>
              <button
                type="button"
                onClick={() => void fireStep(100)}
                disabled={step.state.pending}
                className={fireBtnClass}
              >
                step 100
              </button>
            </>
          }
        />
        <div className="pt-1 text-[10px] text-[color:var(--color-penumbra-dim)]">
          Pause first if you want isolated steps — see Speed control for current rate.
        </div>
      </Section>

      <Section title="recent injections (this session)">
        {history.length === 0 ? (
          <div className="py-1 text-[10px] text-[color:var(--color-penumbra-dim)]">
            no injections fired yet from this UI session.
          </div>
        ) : (
          <ul className="space-y-0.5 text-[10px] text-[color:var(--color-penumbra-text)]">
            {history.map((rec) => (
              <li key={`${rec.at}-${rec.kind}-${rec.tick}`}>
                <span className="text-[color:var(--color-penumbra-dim)]">tick {rec.tick}</span>
                {" — "}
                <span className="text-[color:var(--color-penumbra-cyan)]">{rec.kind}</span>{" "}
                <span className="text-[color:var(--color-penumbra-muted)]">
                  {JSON.stringify(rec.payload)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
