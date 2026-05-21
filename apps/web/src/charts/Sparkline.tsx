/**
 * Tiny monospace-friendly inline SVG sparkline.
 *
 * Default 80×20 px, no axes, no labels — just the shape of a metric
 * over its last N values. Designed to sit alongside a numeric cell.
 */

interface Props {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  fillColor?: string;
  className?: string;
}

export function Sparkline({
  values,
  width = 80,
  height = 18,
  color = "var(--color-penumbra-cyan)",
  fillColor = "color-mix(in srgb, var(--color-penumbra-cyan) 18%, transparent)",
  className,
}: Props) {
  if (values.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className={className}
        role="img"
        aria-label="sparkline"
      >
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="var(--color-penumbra-dim)"
          strokeDasharray="2 2"
          strokeWidth={0.6}
        />
      </svg>
    );
  }

  const finite = values.filter((v) => Number.isFinite(v));
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const range = max - min || 1;
  const stepX = width / (values.length - 1);

  const points = values.map((v, i) => {
    const x = i * stepX;
    const norm = Number.isFinite(v) ? (v - min) / range : 0;
    // Invert Y: SVG origin top-left, but we want larger values "up"
    const y = height - norm * (height - 2) - 1;
    return [x, y] as const;
  });

  const polyline = points.map(([x, y]) => `${x},${y}`).join(" ");
  const first = points[0];
  const last = points[points.length - 1];
  const fillPath =
    first && last
      ? `M ${first[0]},${height} ` +
        points.map(([x, y]) => `L ${x},${y}`).join(" ") +
        ` L ${last[0]},${height} Z`
      : "";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      role="img"
      aria-label="sparkline"
    >
      <path d={fillPath} fill={fillColor} />
      <polyline points={polyline} fill="none" stroke={color} strokeWidth={1.2} />
    </svg>
  );
}
