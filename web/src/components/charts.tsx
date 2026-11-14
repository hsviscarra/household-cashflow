import { useState, type ReactNode } from "react";
import { short } from "../money";
import { useWidth, niceTicks, topRounded, Tooltip, IN, OUT, PAD } from "./chart/base";

export { type BarDatum, MonthBars } from "./chart/MonthBars";

export { type LineDatum, TrendLine } from "./chart/TrendLine";

export { type StackDatum, StackedColumns } from "./chart/StackedColumns";

export { Legend, niceTicks } from "./chart/base";

export type ColumnDatum = {
  key: string;
  label: string;
  in: number;
  out: number;
  plan?: boolean;
  selected?: boolean;
  tooltip: ReactNode;
};

/** Money in and out per month: two columns per month on one axis. */
export function InOutColumns({
  data,
  title,
  onSelect,
}: {
  data: ColumnDatum[];
  title: string;
  onSelect?: (key: string) => void;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const height = 240;
  const max = Math.max(1, ...data.flatMap((d) => [d.in, d.out]));
  const ticks = niceTicks(0, max);
  const top = ticks[ticks.length - 1];
  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const band = plotW / Math.max(1, data.length);
  const bar = Math.min(24, Math.max(4, (band - 10) / 2));
  const y = (v: number) => PAD.top + plotH - (v / top) * plotH;

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
          const op = d.plan ? 0.35 : 1;
          return (
            <g key={d.key}>
              {(hover === i || d.selected) && (
                <rect
                  x={cx - band / 2}
                  y={PAD.top}
                  width={band}
                  height={plotH}
                  rx={8}
                  fill={d.selected ? "var(--color-info-bg)" : "var(--color-surface)"}
                />
              )}
              <path d={topRounded(cx - bar - 1, y(d.in), bar, y(0) - y(d.in))} fill={IN} opacity={op} />
              <path d={topRounded(cx + 1, y(d.out), bar, y(0) - y(d.out))} fill={OUT} opacity={op} />
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
                data-testid={`col-${d.key}`}
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
                aria-pressed={onSelect ? !!d.selected : undefined}
                aria-label={d.label}
              />
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
