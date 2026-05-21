/**
 * Bar chart for BERTopic topic sizes.
 *
 * Used by DetailModal when the user clicks the `topics` cell.
 */

interface Props {
  topicSizes: Record<string, number>;
  topWords: Record<string, string[]>;
  width?: number;
  height?: number;
}

export function TopicsBar({ topicSizes, topWords, width = 560, height = 260 }: Props) {
  const entries = Object.entries(topicSizes)
    .map(([id, count]) => ({ id, count, words: topWords[id] ?? [] }))
    .sort((a, b) => b.count - a.count);

  if (entries.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center text-xs text-[color:var(--color-penumbra-muted)]">
        no topics surfaced yet — BERTopic needs ≥ 40 utterances
      </div>
    );
  }

  const margin = { top: 8, right: 16, bottom: 14, left: 32 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  const maxCount = Math.max(...entries.map((e) => e.count));
  const barH = plotH / entries.length - 4;

  return (
    <div className="font-mono">
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="topic sizes">
        {entries.map((e, i) => {
          const y = margin.top + i * (barH + 4);
          const w = (e.count / maxCount) * plotW;
          return (
            <g key={e.id}>
              <text
                x={margin.left - 4}
                y={y + barH / 2}
                textAnchor="end"
                dominantBaseline="central"
                fontSize={10}
                fill="var(--color-penumbra-muted)"
              >
                #{e.id}
              </text>
              <rect
                x={margin.left}
                y={y}
                width={Math.max(2, w)}
                height={barH}
                fill="color-mix(in srgb, var(--color-penumbra-cyan) 35%, transparent)"
                stroke="var(--color-penumbra-cyan)"
                strokeWidth={0.6}
              />
              <text
                x={margin.left + Math.max(6, w) + 4}
                y={y + barH / 2}
                dominantBaseline="central"
                fontSize={10}
                fill="var(--color-penumbra-text)"
              >
                {e.count} · {e.words.slice(0, 3).join(" · ")}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
