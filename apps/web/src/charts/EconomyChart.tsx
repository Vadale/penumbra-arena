/**
 * City-economy aggregate: category mix + top sellers + basket size.
 *
 * Three small charts laid out in one modal:
 *   1) horizontal bar chart of units sold per category (food, hygiene,
 *      tools, luxury, medicine)
 *   2) ranked list of top-selling products with units + revenue
 *   3) histogram of basket sizes (units per agent-tick)
 */

import type { EconomySnapshot } from "../streams/dashboard";

interface Props {
  data: EconomySnapshot;
  width?: number;
  height?: number;
}

const CATEGORY_COLOR: Record<string, string> = {
  food: "oklch(0.74 0.18 95)",
  hygiene: "oklch(0.78 0.16 180)",
  tools: "oklch(0.66 0.12 50)",
  luxury: "oklch(0.78 0.18 320)",
  medicine: "oklch(0.74 0.17 145)",
};

export function EconomyChart({ data, width = 560 }: Props) {
  const { total_purchases, total_revenue, category_counts, top_products, basket_histogram } = data;
  const cats = Object.entries(category_counts).sort((a, b) => b[1] - a[1]);
  const catMax = cats.length > 0 ? Math.max(...cats.map(([, v]) => v)) : 1;

  const basketMax =
    basket_histogram.length > 0 ? Math.max(...basket_histogram.map(([, c]) => c)) : 1;
  const basketTotalQty = basket_histogram.reduce((s, [k, c]) => s + k * c, 0);
  const basketTotalRows = basket_histogram.reduce((s, [, c]) => s + c, 0);
  const avgBasket = basketTotalRows > 0 ? basketTotalQty / basketTotalRows : 0;

  return (
    <div className="font-mono space-y-3">
      {/* headline numbers */}
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="purchases" value={total_purchases.toLocaleString()} accent />
        <Stat label="revenue" value={total_revenue.toFixed(0)} accent />
        <Stat label="avg basket" value={avgBasket.toFixed(2)} />
      </div>

      {/* categories */}
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          category mix (units sold)
        </div>
        <svg
          viewBox={`0 0 ${width} ${cats.length * 22 + 6}`}
          width="100%"
          role="img"
          aria-label="category mix bars"
        >
          {cats.map(([cat, count], i) => {
            const y = i * 22 + 4;
            const w = catMax > 0 ? (count / catMax) * (width - 140) : 0;
            return (
              <g key={cat}>
                <text
                  x={6}
                  y={y + 11}
                  fontSize={10}
                  dominantBaseline="central"
                  fill="var(--color-penumbra-muted)"
                >
                  {cat}
                </text>
                <rect
                  x={70}
                  y={y}
                  width={Math.max(2, w)}
                  height={16}
                  fill={CATEGORY_COLOR[cat] ?? "var(--color-penumbra-cyan)"}
                  opacity={0.78}
                />
                <text
                  x={74 + Math.max(2, w)}
                  y={y + 11}
                  fontSize={10}
                  dominantBaseline="central"
                  fill="var(--color-penumbra-text)"
                >
                  {count.toLocaleString()}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* top products */}
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
          top sellers
        </div>
        <table className="w-full text-[11px]">
          <thead className="text-[color:var(--color-penumbra-dim)]">
            <tr>
              <th className="text-left font-normal">product</th>
              <th className="text-right font-normal">units</th>
              <th className="text-right font-normal">revenue</th>
            </tr>
          </thead>
          <tbody>
            {top_products.map(([name, units, rev]) => (
              <tr key={name} className="border-t border-[color:var(--color-penumbra-border)]">
                <td className="py-0.5 text-[color:var(--color-penumbra-text)]">{name}</td>
                <td className="py-0.5 text-right tabular-nums text-[color:var(--color-penumbra-cyan)]">
                  {units}
                </td>
                <td className="py-0.5 text-right tabular-nums text-[color:var(--color-penumbra-text)]">
                  {rev.toFixed(1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* basket histogram */}
      {basket_histogram.length > 0 && (
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
            basket-size distribution (units per agent visit)
          </div>
          <svg viewBox="0 0 560 120" width="100%" role="img" aria-label="basket histogram">
            {basket_histogram.map(([size, count], i) => {
              const w = 30;
              const x = 30 + i * (w + 6);
              const h = basketMax > 0 ? (count / basketMax) * 90 : 0;
              return (
                <g key={`b${size}`}>
                  <rect
                    x={x}
                    y={100 - h}
                    width={w}
                    height={h}
                    fill="var(--color-penumbra-cyan)"
                    opacity={0.45}
                    stroke="var(--color-penumbra-cyan)"
                  />
                  <text
                    x={x + w / 2}
                    y={114}
                    textAnchor="middle"
                    fontSize={9}
                    fill="var(--color-penumbra-muted)"
                  >
                    {size === 10 ? "10+" : size}
                  </text>
                  <text
                    x={x + w / 2}
                    y={96 - h}
                    textAnchor="middle"
                    fontSize={9}
                    fill="var(--color-penumbra-text)"
                  >
                    {count}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="border border-[color:var(--color-penumbra-border)] bg-[color:var(--color-penumbra-bg)] px-2 py-1">
      <div className="text-[8px] uppercase tracking-wider text-[color:var(--color-penumbra-dim)]">
        {label}
      </div>
      <div
        className={`tabular-nums ${accent ? "text-[color:var(--color-penumbra-cyan)]" : "text-[color:var(--color-penumbra-text)]"}`}
      >
        {value}
      </div>
    </div>
  );
}
