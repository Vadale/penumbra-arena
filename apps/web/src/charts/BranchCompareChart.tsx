/**
 * Branch compare — split-view side-by-side mode for world branches.
 *
 * Concept taught: counterfactual visualisation. Two world branches
 * advanced independently from the same root snapshot can be compared
 * across simple time-series (mean wealth, position dispersion, tick
 * count). The chart renders them side-by-side with a SHARED y-axis
 * scale so the visual comparison is honest.
 *
 * Backend assumption: the existing `/world/branches` and
 * `/world/branches/compare` endpoints expose only a single snapshot
 * per branch (positions + wealth + tick at the current moment). A
 * proper per-branch time-series endpoint isn't in the API yet — so
 * we DERIVE pseudo time-series on the frontend by perturbing the
 * snapshot deterministically from the branch_id hash. This is
 * labelled clearly in the UI as a demo until the backend exposes
 * `/world/branches/{id}/timeseries?metric=X`.
 */

import { useEffect, useMemo, useState } from "react";
import { Stat } from "./_shared";

interface Branch {
  branch_id: string;
  parent_tick: number;
  current_tick: number;
  n_agents: number;
}

interface CompareRow {
  branch_id: string;
  current_tick: number;
  positions: number[];
  wealth: number[];
  n_agents: number;
}

type Metric = "wealth_mean" | "position_dispersion" | "tick";

const METRICS: { id: Metric; label: string }[] = [
  { id: "wealth_mean", label: "mean wealth" },
  { id: "position_dispersion", label: "position σ" },
  { id: "tick", label: "tick count" },
];

const TIMESERIES_LENGTH = 80;

function hashString(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h;
}

function mulberry32(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function meanArr(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((s, v) => s + v, 0) / values.length;
}

function stdArr(values: number[]): number {
  if (values.length === 0) return 0;
  const m = meanArr(values);
  const v = values.reduce((s, x) => s + (x - m) * (x - m), 0) / values.length;
  return Math.sqrt(v);
}

/**
 * Derive a pseudo time-series for a metric from the snapshot. The
 * series is deterministic per branch_id (so swapping A↔B is honest).
 * Real backend endpoint would replace this with actual logged values.
 */
function deriveTimeseries(row: CompareRow, metric: Metric): number[] {
  const baseValue = (() => {
    switch (metric) {
      case "wealth_mean":
        return meanArr(row.wealth);
      case "position_dispersion":
        return stdArr(row.positions);
      case "tick":
        return row.current_tick;
    }
  })();
  const seed = hashString(`${row.branch_id}:${metric}`);
  const rng = mulberry32(seed);
  const out: number[] = [];
  let value = baseValue * 0.85;
  const drift = (baseValue - value) / TIMESERIES_LENGTH;
  for (let i = 0; i < TIMESERIES_LENGTH; i++) {
    const noise = (rng() - 0.5) * Math.max(0.1, Math.abs(baseValue) * 0.08);
    value += drift + noise;
    out.push(value);
  }
  out[out.length - 1] = baseValue;
  return out;
}

interface MiniChartProps {
  values: number[];
  label: string;
  yMin: number;
  yMax: number;
  accent?: boolean;
}

function MiniChart({ values, label, yMin, yMax, accent }: MiniChartProps) {
  const W = 280;
  const H = 120;
  const M = { top: 8, right: 8, bottom: 16, left: 28 };
  const plotW = W - M.left - M.right;
  const plotH = H - M.top - M.bottom;
  const range = yMax - yMin || 1;
  const xStep = values.length > 1 ? plotW / (values.length - 1) : plotW;
  const stroke = accent
    ? "var(--color-penumbra-cyan)"
    : "color-mix(in srgb, var(--color-penumbra-cyan) 60%, var(--color-penumbra-ember) 40%)";
  const points = values
    .map((v, i) => {
      const x = M.left + i * xStep;
      const y = M.top + (1 - (v - yMin) / range) * plotH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-2">
      <div className="mb-1 text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
        <line
          x1={M.left}
          y1={M.top}
          x2={M.left}
          y2={M.top + plotH}
          stroke="var(--color-penumbra-border)"
          strokeWidth={0.5}
        />
        <line
          x1={M.left}
          y1={M.top + plotH}
          x2={M.left + plotW}
          y2={M.top + plotH}
          stroke="var(--color-penumbra-border)"
          strokeWidth={0.5}
        />
        <text
          x={M.left - 3}
          y={M.top + 6}
          fontSize={8}
          textAnchor="end"
          fill="var(--color-penumbra-muted)"
        >
          {yMax.toFixed(2)}
        </text>
        <text
          x={M.left - 3}
          y={M.top + plotH}
          fontSize={8}
          textAnchor="end"
          fill="var(--color-penumbra-muted)"
        >
          {yMin.toFixed(2)}
        </text>
        <polyline points={points} fill="none" stroke={stroke} strokeWidth={1.3} />
      </svg>
    </div>
  );
}

export function BranchCompareChart() {
  const [branches, setBranches] = useState<Branch[]>([]);
  const [aId, setAId] = useState<string>("");
  const [bId, setBId] = useState<string>("");
  const [rows, setRows] = useState<CompareRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshList = async () => {
    try {
      const r = await fetch("/world/branches");
      if (!r.ok) return;
      const body = (await r.json()) as { branches?: Branch[] };
      setBranches(body.branches ?? []);
    } catch {
      // soft fail
    }
  };

  useEffect(() => {
    void refreshList();
    const t = window.setInterval(refreshList, 5000);
    return () => window.clearInterval(t);
  }, []);

  // Whenever both A and B are picked, fetch their compare snapshot.
  useEffect(() => {
    if (aId === "" || bId === "") {
      setRows([]);
      return;
    }
    const ids = aId === bId ? [aId] : [aId, bId];
    let cancelled = false;
    setBusy(true);
    setError(null);
    void (async () => {
      try {
        const r = await fetch("/world/branches/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ branch_ids: ids }),
        });
        if (cancelled) return;
        if (!r.ok) {
          setError(`compare failed (${r.status})`);
          setRows([]);
          return;
        }
        const body = (await r.json()) as { branches?: CompareRow[] };
        setRows(body.branches ?? []);
      } catch {
        if (!cancelled) {
          setError("compare request failed");
          setRows([]);
        }
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [aId, bId]);

  const rowA = useMemo(() => rows.find((r) => r.branch_id === aId) ?? null, [rows, aId]);
  const rowB = useMemo(
    () => rows.find((r) => r.branch_id === bId) ?? (aId === bId ? (rows[0] ?? null) : null),
    [rows, aId, bId],
  );

  const swap = () => {
    setAId(bId);
    setBId(aId);
  };

  const reset = () => {
    setAId("");
    setBId("");
    setRows([]);
  };

  // Pre-compute the shared y-axis range PER metric across both series.
  const series = useMemo(() => {
    if (rowA === null || rowB === null) return null;
    const out: Record<Metric, { a: number[]; b: number[]; min: number; max: number }> = {
      wealth_mean: { a: [], b: [], min: 0, max: 0 },
      position_dispersion: { a: [], b: [], min: 0, max: 0 },
      tick: { a: [], b: [], min: 0, max: 0 },
    };
    for (const m of METRICS) {
      const a = deriveTimeseries(rowA, m.id);
      const b = deriveTimeseries(rowB, m.id);
      const all = [...a, ...b];
      const min = Math.min(...all);
      const max = Math.max(...all);
      const pad = Math.max(0.01, (max - min) * 0.05);
      out[m.id] = { a, b, min: min - pad, max: max + pad };
    }
    return out;
  }, [rowA, rowB]);

  return (
    <div className="font-mono space-y-3">
      <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
        Pick two branches and compare their mean wealth, position dispersion, and tick count
        side-by-side. Each metric pair shares a y-axis scale so visual heights are honest.
        Time-series are derived on the frontend (deterministic per branch_id) — demo until the
        backend exposes <code>/world/branches/{`{id}`}/timeseries?metric=X</code>.
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[10px]">
        <label
          htmlFor="branch-a"
          className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]"
        >
          branch A
        </label>
        <select
          id="branch-a"
          value={aId}
          onChange={(e) => setAId(e.target.value)}
          className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 py-0.5 text-[11px] text-[color:var(--color-penumbra-text)]"
        >
          <option value="">—</option>
          {branches.map((b) => (
            <option key={b.branch_id} value={b.branch_id}>
              {b.branch_id} (t={b.current_tick})
            </option>
          ))}
        </select>
        <label
          htmlFor="branch-b"
          className="uppercase tracking-wider text-[color:var(--color-penumbra-dim)]"
        >
          branch B
        </label>
        <select
          id="branch-b"
          value={bId}
          onChange={(e) => setBId(e.target.value)}
          className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 py-0.5 text-[11px] text-[color:var(--color-penumbra-text)]"
        >
          <option value="">—</option>
          {branches.map((b) => (
            <option key={b.branch_id} value={b.branch_id}>
              {b.branch_id} (t={b.current_tick})
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={swap}
          disabled={aId === "" || bId === ""}
          aria-label="Swap A and B"
          className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-0.5 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)] disabled:opacity-40"
        >
          swap
        </button>
        <button
          type="button"
          onClick={reset}
          aria-label="Reset selection"
          className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-0.5 text-[10px] uppercase text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
        >
          reset
        </button>
      </div>

      {branches.length === 0 && (
        <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
          no branches exist yet — create some from the "world — branches" tile first.
        </div>
      )}

      {error !== null && (
        <div className="text-[10px] text-[color:var(--color-penumbra-ember)]">{error}</div>
      )}

      {busy && <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">loading…</div>}

      {series !== null && rowA !== null && rowB !== null && (
        <div className="space-y-3">
          {METRICS.map((m) => {
            const s = series[m.id];
            return (
              <div key={m.id}>
                <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-cyan)]">
                  {m.label}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <MiniChart
                    values={s.a}
                    label={`A · ${rowA.branch_id}`}
                    yMin={s.min}
                    yMax={s.max}
                    accent
                  />
                  <MiniChart
                    values={s.b}
                    label={`B · ${rowB.branch_id}`}
                    yMin={s.min}
                    yMax={s.max}
                  />
                </div>
              </div>
            );
          })}

          <div className="grid grid-cols-4 gap-2 text-[10px]">
            <Stat label="A tick" value={rowA.current_tick} digits={0} accent />
            <Stat label="B tick" value={rowB.current_tick} digits={0} />
            <Stat label="A mean $" value={meanArr(rowA.wealth)} digits={2} accent />
            <Stat label="B mean $" value={meanArr(rowB.wealth)} digits={2} />
          </div>
        </div>
      )}
    </div>
  );
}
