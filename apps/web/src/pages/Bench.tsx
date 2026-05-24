/**
 * Penumbra-Bench public leaderboard page.
 *
 * Reads `state/bench/*.json` via the `/benchmark/leaderboard`
 * endpoint and renders a sortable per-tier table. Clicking a row
 * fetches the full submission detail through
 * `/benchmark/submission/{filename}` and expands it inline.
 */

import { useEffect, useMemo, useState } from "react";

type Tier = "tiny" | "small" | "medium" | "large";
const TIERS: readonly Tier[] = ["tiny", "small", "medium", "large"] as const;
const TASK_IDS = ["PA1", "AR1", "MC1", "PB1", "LR1"] as const;
type TaskId = (typeof TASK_IDS)[number];

interface LeaderboardEntry {
  rank: number;
  filename: string;
  submitter: string;
  method: string;
  tier: string;
  composite_score: number;
  task_scores: Record<string, number>;
  hardware: string;
  pytorch_version: string;
  penumbra_commit: string;
  submission_timestamp_ns: number;
}

interface LeaderboardPayload {
  available: boolean;
  tier: string;
  n_total: number;
  entries: LeaderboardEntry[];
}

interface SubmissionTask {
  task_id: string;
  score: number;
  metric_values: Record<string, number>;
  n_episodes: number;
  wall_seconds: number;
}

interface SubmissionPayload {
  available: boolean;
  filename: string;
  submitter: string;
  method: string;
  tier: string;
  tasks: SubmissionTask[];
  composite_score: number;
  submission_timestamp_ns: number;
  penumbra_commit: string;
  pytorch_version: string;
  hardware: string;
}

type SortKey = "rank" | "submitter" | "method" | "composite" | TaskId | "hardware" | "timestamp";
type SortDir = "asc" | "desc";

function formatTimestamp(ns: number): string {
  if (!ns) return "—";
  const ms = Math.floor(ns / 1_000_000);
  const d = new Date(ms);
  return d.toISOString().replace("T", " ").slice(0, 19);
}

function compareEntries(a: LeaderboardEntry, b: LeaderboardEntry, key: SortKey): number {
  switch (key) {
    case "rank":
      return a.rank - b.rank;
    case "submitter":
      return a.submitter.localeCompare(b.submitter);
    case "method":
      return a.method.localeCompare(b.method);
    case "composite":
      return a.composite_score - b.composite_score;
    case "hardware":
      return a.hardware.localeCompare(b.hardware);
    case "timestamp":
      return a.submission_timestamp_ns - b.submission_timestamp_ns;
    default: {
      const av = a.task_scores[key] ?? 0;
      const bv = b.task_scores[key] ?? 0;
      return av - bv;
    }
  }
}

export function Bench() {
  const [tier, setTier] = useState<Tier>("tiny");
  const [data, setData] = useState<LeaderboardPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("composite");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<SubmissionPayload | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`/benchmark/leaderboard?tier=${tier}&limit=50`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`status ${res.status}`);
        return (await res.json()) as LeaderboardPayload;
      })
      .then((body) => {
        if (cancelled) return;
        setData(body);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "request failed");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tier]);

  const sorted = useMemo(() => {
    if (!data) return [];
    const arr = [...data.entries];
    arr.sort((a, b) => {
      const cmp = compareEntries(a, b, sortKey);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [data, sortKey, sortDir]);

  const onSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "submitter" || key === "method" || key === "hardware" ? "asc" : "desc");
    }
  };

  const onRowClick = async (filename: string) => {
    if (expanded === filename) {
      setExpanded(null);
      setDetail(null);
      return;
    }
    setExpanded(filename);
    setDetail(null);
    setDetailLoading(true);
    try {
      const res = await fetch(`/benchmark/submission/${encodeURIComponent(filename)}`);
      if (res.ok) {
        setDetail((await res.json()) as SubmissionPayload);
      }
    } catch {
      // swallow — the detail section will simply show "failed".
    }
    setDetailLoading(false);
  };

  return (
    <div className="flex h-full flex-col bg-[color:var(--color-penumbra-bg)] text-[color:var(--color-penumbra-text)]">
      <header className="flex items-center justify-between border-b border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] px-4 py-2">
        <div className="flex items-baseline gap-3">
          <a
            href="/"
            className="text-sm font-semibold tracking-tight text-[color:var(--color-penumbra-text)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            penumbra
          </a>
          <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-penumbra-muted)]">
            bench · public leaderboard
          </span>
        </div>
        <nav className="flex items-center gap-3 text-[11px]">
          <a
            href="/operator"
            className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            operator
          </a>
          <a
            href="/"
            className="rounded-sm border border-[color:var(--color-penumbra-border)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-cyan)]"
          >
            ← dashboard
          </a>
        </nav>
      </header>

      <div className="flex items-center gap-2 border-b border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] px-4 py-2 text-[10px] uppercase tracking-[0.18em]">
        {TIERS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => {
              setTier(t);
              setExpanded(null);
              setDetail(null);
            }}
            className={
              tier === t
                ? "border-b border-[color:var(--color-penumbra-cyan)] pb-0.5 text-[color:var(--color-penumbra-cyan)]"
                : "pb-0.5 text-[color:var(--color-penumbra-muted)] hover:text-[color:var(--color-penumbra-text)]"
            }
          >
            {t}
          </button>
        ))}
        <span className="ml-auto text-[10px] normal-case tracking-normal text-[color:var(--color-penumbra-dim)]">
          {data ? `${data.n_total} submission${data.n_total === 1 ? "" : "s"}` : ""}
        </span>
      </div>

      <main className="flex-1 overflow-auto px-4 py-3">
        {loading && (
          <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">loading…</div>
        )}
        {error && (
          <div className="font-mono text-xs text-[color:var(--color-penumbra-ember)]">
            failed: {error}
          </div>
        )}
        {!loading && !error && data && data.entries.length === 0 && (
          <div className="font-mono text-xs text-[color:var(--color-penumbra-muted)]">
            no submissions for tier "{tier}" yet — run{" "}
            <code className="text-[color:var(--color-penumbra-cyan)]">
              uv run python -m penumbra_learning.benchmark
            </code>{" "}
            to contribute.
          </div>
        )}
        {!loading && !error && data && data.entries.length > 0 && (
          <table className="min-w-full font-mono text-[11px]">
            <thead>
              <tr className="border-b border-[color:var(--color-penumbra-border)] text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
                <Th label="rank" sortKey="rank" cur={sortKey} dir={sortDir} onSort={onSort} />
                <Th
                  label="submitter"
                  sortKey="submitter"
                  cur={sortKey}
                  dir={sortDir}
                  onSort={onSort}
                />
                <Th label="method" sortKey="method" cur={sortKey} dir={sortDir} onSort={onSort} />
                <Th
                  label="composite"
                  sortKey="composite"
                  cur={sortKey}
                  dir={sortDir}
                  onSort={onSort}
                />
                {TASK_IDS.map((t) => (
                  <Th key={t} label={t} sortKey={t} cur={sortKey} dir={sortDir} onSort={onSort} />
                ))}
                <Th
                  label="hardware"
                  sortKey="hardware"
                  cur={sortKey}
                  dir={sortDir}
                  onSort={onSort}
                />
                <Th
                  label="timestamp"
                  sortKey="timestamp"
                  cur={sortKey}
                  dir={sortDir}
                  onSort={onSort}
                />
              </tr>
            </thead>
            <tbody>
              {sorted.map((entry) => (
                <Row
                  key={entry.filename}
                  entry={entry}
                  expanded={expanded === entry.filename}
                  detail={expanded === entry.filename ? detail : null}
                  detailLoading={expanded === entry.filename && detailLoading}
                  onClick={() => void onRowClick(entry.filename)}
                />
              ))}
            </tbody>
          </table>
        )}
      </main>
    </div>
  );
}

function Th({
  label,
  sortKey,
  cur,
  dir,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  cur: SortKey;
  dir: SortDir;
  onSort: (k: SortKey) => void;
}) {
  const active = cur === sortKey;
  const marker = active ? (dir === "asc" ? " ↑" : " ↓") : "";
  return (
    <th className="px-2 py-1 text-left font-normal">
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={
          active
            ? "text-[color:var(--color-penumbra-cyan)]"
            : "text-[color:var(--color-penumbra-dim)] hover:text-[color:var(--color-penumbra-text)]"
        }
      >
        {label}
        {marker}
      </button>
    </th>
  );
}

function Row({
  entry,
  expanded,
  detail,
  detailLoading,
  onClick,
}: {
  entry: LeaderboardEntry;
  expanded: boolean;
  detail: SubmissionPayload | null;
  detailLoading: boolean;
  onClick: () => void;
}) {
  return (
    <>
      <tr
        onClick={onClick}
        className={`cursor-pointer border-b border-[color:var(--color-penumbra-border)] hover:bg-[color:var(--color-penumbra-panel)] ${expanded ? "bg-[color:var(--color-penumbra-panel)]" : ""}`}
      >
        <td className="px-2 py-1 tabular-nums text-[color:var(--color-penumbra-cyan)]">
          {entry.rank}
        </td>
        <td className="px-2 py-1">{entry.submitter}</td>
        <td className="px-2 py-1 text-[color:var(--color-penumbra-muted)]">{entry.method}</td>
        <td className="px-2 py-1 tabular-nums text-[color:var(--color-penumbra-cyan)]">
          {entry.composite_score.toFixed(3)}
        </td>
        {TASK_IDS.map((t) => (
          <td key={t} className="px-2 py-1 tabular-nums">
            {(entry.task_scores[t] ?? 0).toFixed(3)}
          </td>
        ))}
        <td className="px-2 py-1 text-[color:var(--color-penumbra-muted)]">{entry.hardware}</td>
        <td className="px-2 py-1 text-[color:var(--color-penumbra-dim)]">
          {formatTimestamp(entry.submission_timestamp_ns)}
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)]">
          <td colSpan={4 + TASK_IDS.length + 2} className="px-4 py-3">
            {detailLoading && (
              <div className="text-[10px] text-[color:var(--color-penumbra-muted)]">
                loading detail…
              </div>
            )}
            {!detailLoading && detail && <DetailBlock detail={detail} />}
            {!detailLoading && !detail && (
              <div className="text-[10px] text-[color:var(--color-penumbra-ember)]">
                failed to load submission detail
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function DetailBlock({ detail }: { detail: SubmissionPayload }) {
  return (
    <div className="space-y-2 text-[10px] font-mono">
      <div className="grid grid-cols-4 gap-2">
        <Meta label="filename" value={detail.filename} />
        <Meta label="commit" value={detail.penumbra_commit.slice(0, 12) || "—"} />
        <Meta label="pytorch" value={detail.pytorch_version || "—"} />
        <Meta label="hardware" value={detail.hardware || "—"} />
      </div>
      <div className="text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        per-task breakdown
      </div>
      <table className="min-w-full">
        <thead>
          <tr className="text-[9px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
            <th className="px-2 py-1 text-left font-normal">task</th>
            <th className="px-2 py-1 text-left font-normal">score</th>
            <th className="px-2 py-1 text-left font-normal">episodes</th>
            <th className="px-2 py-1 text-left font-normal">wall (s)</th>
            <th className="px-2 py-1 text-left font-normal">metrics</th>
          </tr>
        </thead>
        <tbody>
          {detail.tasks.map((t) => (
            <tr key={t.task_id} className="border-t border-[color:var(--color-penumbra-border)]">
              <td className="px-2 py-1 text-[color:var(--color-penumbra-cyan)]">{t.task_id}</td>
              <td className="px-2 py-1 tabular-nums">{t.score.toFixed(4)}</td>
              <td className="px-2 py-1 tabular-nums">{t.n_episodes}</td>
              <td className="px-2 py-1 tabular-nums">{t.wall_seconds.toFixed(3)}</td>
              <td className="px-2 py-1 text-[color:var(--color-penumbra-muted)]">
                {Object.entries(t.metric_values)
                  .map(([k, v]) => `${k}=${v.toFixed(4)}`)
                  .join(" · ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div className="text-[10px] text-[color:var(--color-penumbra-text)]">{value}</div>
    </div>
  );
}
