import { type ReactNode, useState } from "react";
import { useWidth, niceTicks, PAD, Tooltip, topRounded, OUT } from "./base";
import { short } from "../../money";

export type BarDatum = { key: string; label: string; value: number; tooltip: ReactNode; selected?: boolean };

/** One series per month (spending); the selected month in full color, the others lighter.
 * Each column is a button when onSelect is given. */
export function MonthBars({
  data,
  title,
  onSelect,
}: {
  data: BarDatum[];
  title: string;
  onSelect?: (key: string) => void;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const height = 200;
  const ticks = niceTicks(0, Math.max(1, ...data.map((d) => d.value)));
  const top = ticks[ticks.length - 1];
  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const band = plotW / Math.max(1, data.length);
  const bar = Math.min(24, Math.max(4, band - 4));
  const y = (v: number) => PAD.top + plotH - (Math.max(0, v) / top) * plotH;
  return (
    <figure ref={ref} className="relative">
      <figcaption className="sr-only">{title}</figcaption>
      {hover !== null && (
        <Tooltip x={PAD.left + band * (hover + 0.5)} width={width}>
          {data[hover].tooltip}
        </Tooltip>
      )}
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="block max-w-full"
        role="img"
        aria-label={title}
        onMouseLeave={() => setHover(null)}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line
              x1={PAD.left}
              x2={width - PAD.right}
              y1={y(t)}
              y2={y(t)}
              stroke="var(--color-line)"
              strokeWidth={1}
            />
            <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" fontSize={11} fill="var(--color-muted)">
              {short(t)}
            </text>
          </g>
        ))}
        {data.map((d, i) => {
          const cx = PAD.left + band * (i + 0.5);
          return (
            <g key={d.key}>
              {hover === i && (
                <rect x={cx - band / 2} y={PAD.top} width={band} height={plotH} fill="var(--color-surface)" />
              )}
              <path
                d={topRounded(cx - bar / 2, y(d.value), bar, y(0) - y(d.value))}
                fill={OUT}
                opacity={d.selected ? 1 : 0.45}
              />
              <text
                x={cx}
                y={height - 8}
                textAnchor="middle"
                fontSize={11}
                fontWeight={d.selected ? 700 : 400}
                fill={d.selected ? "var(--color-ink)" : "var(--color-muted)"}
              >
                {d.label}
              </text>
              <rect
                data-testid={`bar-${d.key}`}
                x={cx - band / 2}
                y={PAD.top}
                width={band}
                height={plotH + PAD.bottom}
                fill="transparent"
                className={onSelect ? "cursor-pointer" : undefined}
                onMouseEnter={() => setHover(i)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                onClick={() => onSelect?.(d.key)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") onSelect?.(d.key);
                }}
                tabIndex={0}
                role={onSelect ? "button" : undefined}
                aria-label={d.label}
              />
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
