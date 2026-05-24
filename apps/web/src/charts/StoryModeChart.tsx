/**
 * Phase 5 Tier 5 — Story Mode tile.
 *
 * Renders the cross-pillar narrative lessons shipped under
 * `packages/shell_coach/lessons/`. The operator picks a difficulty
 * + pillar filter, sees the matching stories, and clicks one to
 * copy the `psh lesson <id>` command they'll run in the embedded
 * terminal.
 */

import { useEffect, useMemo, useState } from "react";
import { Stat } from "./_shared";

interface Story {
  id: string;
  title: string;
  difficulty: "easy" | "medium" | "hard";
  pillars: string[];
  prereqs: string[];
  command: string;
  blurb: string;
}

interface StoriesResponse {
  available: boolean;
  stories: Story[];
  pillars: string[];
  difficulties: string[];
}

const DIFFICULTY_OPTIONS = ["all", "easy", "medium", "hard"] as const;
type DifficultyFilter = (typeof DIFFICULTY_OPTIONS)[number];

export function StoryModeChart() {
  const [data, setData] = useState<StoriesResponse | null>(null);
  const [difficulty, setDifficulty] = useState<DifficultyFilter>("all");
  const [pillar, setPillar] = useState<string>("all");
  const [selected, setSelected] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch("/coach/stories");
        if (!r.ok) return;
        const body = (await r.json()) as StoriesResponse;
        setData(body);
        if (body.stories[0] && !selected) setSelected(body.stories[0].id);
      } catch {}
    };
    void load();
  }, []);

  const filtered = useMemo(() => {
    if (!data) return [] as Story[];
    return data.stories.filter((story) => {
      if (difficulty !== "all" && story.difficulty !== difficulty) return false;
      if (pillar !== "all" && !story.pillars.includes(pillar)) return false;
      return true;
    });
  }, [data, difficulty, pillar]);

  const current = useMemo<Story | null>(
    () => filtered.find((s) => s.id === selected) ?? filtered[0] ?? null,
    [filtered, selected],
  );

  const copy = async (cmd: string) => {
    try {
      await navigator.clipboard.writeText(cmd);
      setCopied(cmd);
      setTimeout(() => setCopied(null), 1500);
    } catch {}
  };

  if (!data) {
    return (
      <div className="font-mono text-[10px] text-[color:var(--color-penumbra-dim)]">
        loading stories...
      </div>
    );
  }

  return (
    <div className="font-mono space-y-3">
      <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
        Cross-pillar narrative lessons that thread an attack chain through logistics, statistics,
        NN, RL, and crypto. Each one maps to a `psh lesson &lt;id&gt;` run in the embedded terminal.
      </div>

      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <div>
          <label
            htmlFor="story-difficulty"
            className="block uppercase tracking-wider text-[color:var(--color-penumbra-dim)]"
          >
            difficulty
          </label>
          <select
            id="story-difficulty"
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value as DifficultyFilter)}
            className="w-full border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
          >
            {DIFFICULTY_OPTIONS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor="story-pillar"
            className="block uppercase tracking-wider text-[color:var(--color-penumbra-dim)]"
          >
            pillar
          </label>
          <select
            id="story-pillar"
            value={pillar}
            onChange={(e) => setPillar(e.target.value)}
            className="w-full border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-1 text-[11px] text-[color:var(--color-penumbra-text)]"
          >
            <option value="all">all</option>
            {data.pillars.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="stories" value={String(filtered.length)} />
        <Stat label="pillars" value={String(data.pillars.length)} />
        <Stat label="copied" value={copied ? "ok" : "-"} accent={copied !== null} />
      </div>

      <div className="max-h-64 space-y-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="text-[10px] text-[color:var(--color-penumbra-dim)]">
            no stories match this filter
          </div>
        ) : (
          filtered.map((story) => (
            <button
              key={story.id}
              type="button"
              onClick={() => setSelected(story.id)}
              className={`w-full border px-2 py-1 text-left text-[10px] ${
                current?.id === story.id
                  ? "border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)]"
                  : "border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)]"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[color:var(--color-penumbra-text)]">{story.title}</span>
                <span className="text-[10px] uppercase text-[color:var(--color-penumbra-dim)]">
                  {story.difficulty}
                </span>
              </div>
              <div className="text-[10px] text-[color:var(--color-penumbra-muted)]">
                {story.pillars.join(" / ")}
              </div>
            </button>
          ))
        )}
      </div>

      {current && (
        <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] p-2 text-[10px]">
          <div className="mb-1 text-[color:var(--color-penumbra-cyan)]">{current.title}</div>
          <div className="mb-1 text-[color:var(--color-penumbra-muted)]">{current.blurb}</div>
          {current.prereqs.length > 0 && (
            <div className="mb-1 text-[color:var(--color-penumbra-dim)]">
              prereqs: {current.prereqs.join(", ")}
            </div>
          )}
          <div className="flex items-center gap-2">
            <code className="flex-1 truncate border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-panel)] px-1 py-0.5 text-[10px] text-[color:var(--color-penumbra-text)]">
              {current.command}
            </code>
            <button
              type="button"
              onClick={() => void copy(current.command)}
              className="border border-[color:var(--color-penumbra-cyan)] bg-[color:var(--color-penumbra-cyan-bg)] px-2 py-0.5 text-[10px] uppercase text-[color:var(--color-penumbra-cyan)]"
            >
              copy
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
