/**
 * Persistence barcode — pure-SVG visualization of (birth, death) bars.
 *
 * H₀ and H₁ rendered as two stacked groups. Each bar's x-extent is the
 * lifetime of that topological feature: longer = more persistent =
 * more "real" structure. Empty diagrams show a dim placeholder.
 *
 * Concept taught: the barcode is the standard TDA visualization. The
 * eye can pick out the few long bars (real features) vs the many
 * short ones (sampling noise) at a glance.
 */

interface Props {
  h0Bars: [number, number][];
  h1Bars: [number, number][];
  width?: number;
}

const ROW_HEIGHT = 4;
const ROW_GAP = 1;
const MAX_BARS_PER_DIM = 24;
const LABEL_WIDTH = 24;
const PAD = 8;

function maxDeath(bars: [number, number][]): number {
  return bars.reduce((m, [, d]) => Math.max(m, d), 0);
}

export function PersistenceBarcode({ h0Bars, h1Bars, width = 280 }: Props) {
  const trimmedH0 = h0Bars.slice(0, MAX_BARS_PER_DIM);
  const trimmedH1 = h1Bars.slice(0, MAX_BARS_PER_DIM);
  const xMax = Math.max(maxDeath(h0Bars), maxDeath(h1Bars), 1);
  const innerWidth = width - LABEL_WIDTH - PAD * 2;
  const scaleX = (v: number) => LABEL_WIDTH + PAD + (v / xMax) * innerWidth;

  const h0Height = Math.max(trimmedH0.length, 1) * (ROW_HEIGHT + ROW_GAP);
  const h1Height = Math.max(trimmedH1.length, 1) * (ROW_HEIGHT + ROW_GAP);
  const totalHeight = h0Height + h1Height + PAD * 3 + 14;

  if (h0Bars.length === 0 && h1Bars.length === 0) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900/30 p-2 text-[11px] text-slate-500">
        persistence diagram empty — pipeline still warming up
      </div>
    );
  }

  return (
    <svg
      width={width}
      height={totalHeight}
      viewBox={`0 0 ${width} ${totalHeight}`}
      role="img"
      aria-label="persistence barcode"
      className="rounded border border-slate-800 bg-slate-900/30"
    >
      <text x={4} y={12} fill="#94a3b8" fontSize={9} fontFamily="ui-monospace, monospace">
        H₀
      </text>
      {trimmedH0.map((bar, i) => {
        const [birth, death] = bar;
        const y = PAD + i * (ROW_HEIGHT + ROW_GAP);
        return (
          <line
            // biome-ignore lint/suspicious/noArrayIndexKey: bars are positional in the visualization
            key={`h0-${birth.toFixed(6)}-${death.toFixed(6)}-${i}`}
            x1={scaleX(birth)}
            x2={scaleX(death)}
            y1={y + ROW_HEIGHT / 2}
            y2={y + ROW_HEIGHT / 2}
            stroke="#60a5fa"
            strokeWidth={ROW_HEIGHT}
            strokeLinecap="round"
          />
        );
      })}

      <text
        x={4}
        y={h0Height + PAD * 2 + 10}
        fill="#94a3b8"
        fontSize={9}
        fontFamily="ui-monospace, monospace"
      >
        H₁
      </text>
      {trimmedH1.map((bar, i) => {
        const [birth, death] = bar;
        const y = h0Height + PAD * 2 + 14 + i * (ROW_HEIGHT + ROW_GAP);
        return (
          <line
            // biome-ignore lint/suspicious/noArrayIndexKey: bars are positional in the visualization
            key={`h1-${birth.toFixed(6)}-${death.toFixed(6)}-${i}`}
            x1={scaleX(birth)}
            x2={scaleX(death)}
            y1={y + ROW_HEIGHT / 2}
            y2={y + ROW_HEIGHT / 2}
            stroke="#f472b6"
            strokeWidth={ROW_HEIGHT}
            strokeLinecap="round"
          />
        );
      })}

      <line
        x1={LABEL_WIDTH + PAD}
        x2={width - PAD}
        y1={totalHeight - 6}
        y2={totalHeight - 6}
        stroke="#475569"
        strokeWidth={0.5}
      />
      <text
        x={LABEL_WIDTH + PAD}
        y={totalHeight - 1}
        fill="#64748b"
        fontSize={8}
        fontFamily="ui-monospace, monospace"
      >
        0
      </text>
      <text
        x={width - PAD}
        y={totalHeight - 1}
        fill="#64748b"
        fontSize={8}
        textAnchor="end"
        fontFamily="ui-monospace, monospace"
      >
        {xMax.toFixed(2)}
      </text>
    </svg>
  );
}
