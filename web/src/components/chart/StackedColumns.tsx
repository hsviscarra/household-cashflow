import { type ReactNode, useState } from "react";
import { useWidth, niceTicks, PAD, Tooltip, topRounded } from "./base";
import { short } from "../../money";

export type StackDatum = {
  key: string;
  label: string;
  segments: { key: string; value: number; color: string }[];
  /** A second measure drawn as a line over the stacks (statements' spending). */
  line?: number;
  selected?: boolean;
  tooltip: ReactNode;
};

/** Stacked columns per month (spending by aisle), with an optional line over them. Segments are
 * 1px apart so neighbours stay distinct; each column is a button when onSelect is given. */
export function StackedColumns({
  data,
  title,
  onSelect,
}: {
  data: StackDatum[];
  title: string;
  onSelect?: (key: string) => void;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const height = 260;
  const totals = data.map((d) => d.segments.reduce((s, x) => s + Math.max(0, x.value), 0));
  const ticks = niceTicks(0, Math.max(1, ...totals, ...data.map((d) => d.line ?? 0)));
  const top = ticks[ticks.length - 1];
  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const band = plotW / Math.max(1, data.length);
  const bar = Math.min(24, Math.max(6, band - 8));
  const y = (v: number) => PAD.top + plotH - (Math.max(0, v) / top) * plotH;
  const cxOf = (i: number) => PAD.left + band * (i + 0.5);
  // The line breaks where a month has no value (no statements yet).
  const runs: string[] = [];
  let run: string[] = [];
  data.forEach((d, i) => {
    if (d.line === undefined) {
      if (run.length > 1) runs.push(run.join(" "));
      run = [];
    } else run.push(`${cxOf(i)},${y(d.line)}`);
  });
  if (run.length > 1) runs.push(run.join(" "));
  return (
    <figure ref={ref} className="relative">
      <figcaption className="sr-only">{title}</figcaption>
      {hover !== null && (
        <Tooltip x={cxOf(hover)} width={width}>
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
          const cx = cxOf(i);
          let acc = 0;
          const segs = d.segments.filter((s) => s.value > 0);
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
              {segs.map((s, j) => {
                const y0 = y(acc);
                acc += s.value;
                const y1 = y(acc);
                const h = Math.max(0, y0 - y1 - (j < segs.length - 1 ? 1 : 0));
                const last = j === segs.length - 1;
                return last ? (
                  <path key={s.key} d={topRounded(cx - bar / 2, y1, bar, y0 - y1)} fill={s.color} />
                ) : (
                  <rect key={s.key} x={cx - bar / 2} y={y0 - h} width={bar} height={h} fill={s.color} />
                );
              })}
              {(band >= 30 || i % 2 === 0 || d.selected) && (
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
              )}
            </g>
          );
        })}
        {runs.map((pts) => (
          <polyline
            key={pts}
            points={pts}
            fill="none"
            stroke="var(--color-ink)"
            strokeWidth={2}
            strokeLinejoin="round"
          />
        ))}
        {data.map((d, i) =>
          d.line === undefined ? null : (
            <circle
              key={`dot-${d.key}`}
              cx={cxOf(i)}
              cy={y(d.line)}
              r={3.5}
              fill="var(--color-ink)"
              stroke="var(--color-ground)"
              strokeWidth={2}
            />
          ),
        )}
        {data.map((d, i) => (
          <rect
            key={`hit-${d.key}`}
            data-testid={`stack-${d.key}`}
            x={cxOf(i) - band / 2}
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
        ))}
      </svg>
    </figure>
  );
}
