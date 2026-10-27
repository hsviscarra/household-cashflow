import { useEffect, useRef, useState, type ReactNode } from "react";

import { short } from "../money";

// Hand-drawn SVG charts on the Mercado tokens: they follow light and dark mode through CSS
// variables and need no chart library. Specs (docs/design-system.md, Charts): columns at most
// 24px wide with 4px rounded tops, 2px gaps, 2px lines, hairline solid grid, legend always shown.

function useWidth<T extends HTMLElement>(fallback = 640) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(280, entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Round axis bounds and 4-5 clean ticks. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) max = min + 1;
  const span = max - min;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= count) ?? 10 * mag;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Math.round(v * 100) / 100);
  return ticks;
}

function topRounded(x: number, y: number, w: number, h: number, r = 4) {
  if (h <= 0) return "";
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

export function Legend({ items }: { items: { label: string; color: string; faded?: boolean }[] }) {
  return (
    <ul className="flex flex-wrap gap-4 text-sm text-muted">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-2">
          <span
            aria-hidden
            className="inline-block h-3 w-3 rounded-sm"
            style={{ background: i.color, opacity: i.faded ? 0.35 : 1 }}
          />
          {i.label}
        </li>
      ))}
    </ul>
  );
}

function Tooltip({ x, width, children }: { x: number; width: number; children: ReactNode }) {
  const left = Math.min(Math.max(x - 90, 0), width - 180);
  return (
    <div
      role="status"
      className="pointer-events-none absolute top-0 z-10 w-[180px] rounded-xl border border-line bg-ground px-3 py-2 text-sm shadow-sm"
      style={{ left }}
    >
      {children}
    </div>
  );
}

export type ColumnDatum = {
  key: string;
  label: string;
  in: number;
  out: number;
  plan?: boolean;
  tooltip: ReactNode;
};

const IN = "var(--color-flow-in)";
const OUT = "var(--color-flow-out)";
const PAD = { top: 12, right: 8, bottom: 28, left: 44 };

/** Money in and out per month: two columns per month on one axis. */
export function InOutColumns({ data, title }: { data: ColumnDatum[]; title: string }) {
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
              {hover === i && (
                <rect x={cx - band / 2} y={PAD.top} width={band} height={plotH} fill="var(--color-surface)" />
              )}
              <path d={topRounded(cx - bar - 1, y(d.in), bar, y(0) - y(d.in))} fill={IN} opacity={op} />
              <path d={topRounded(cx + 1, y(d.out), bar, y(0) - y(d.out))} fill={OUT} opacity={op} />
              <text x={cx} y={height - 8} textAnchor="middle" fontSize={11} fill="var(--color-muted)">
                {d.label}
              </text>
              <rect
                data-testid={`col-${d.key}`}
                x={cx - band / 2}
                y={PAD.top}
                width={band}
                height={plotH + PAD.bottom}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                tabIndex={0}
                aria-label={d.label}
              />
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

export type LineDatum = { key: string; value: number; tooltip: ReactNode; tick?: string };

/** One series over time (cumulative net), with a zero line and a crosshair. */
export function TrendLine({ data, title }: { data: LineDatum[]; title: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const height = 220;
  const values = data.map((d) => d.value);
  const ticks = niceTicks(Math.min(0, ...values), Math.max(0, ...values));
  const lo = ticks[0];
  const hi = ticks[ticks.length - 1];
  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (data.length < 2 ? plotW / 2 : (i / (data.length - 1)) * plotW);
  const y = (v: number) => PAD.top + plotH - ((v - lo) / (hi - lo || 1)) * plotH;
  const line = data.map((d, i) => `${i ? "L" : "M"}${x(i)},${y(d.value)}`).join("");
  const area = data.length ? `${line}L${x(data.length - 1)},${y(0)}L${x(0)},${y(0)}Z` : "";

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const rel = (e.clientX - box.left - PAD.left) / (plotW || 1);
    setHover(Math.min(data.length - 1, Math.max(0, Math.round(rel * (data.length - 1)))));
  };

  return (
    <figure ref={ref} className="relative">
      <figcaption className="sr-only">{title}</figcaption>
      {hover !== null && data[hover] && (
        <Tooltip x={x(hover)} width={width}>
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
        onMouseMove={onMove}
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
              strokeWidth={t === 0 ? 1.5 : 1}
            />
            <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" fontSize={11} fill="var(--color-muted)">
              {short(t)}
            </text>
          </g>
        ))}
        {data.map((d, i) =>
          d.tick ? (
            <text
              key={d.key}
              x={x(i)}
              y={height - 8}
              textAnchor="middle"
              fontSize={11}
              fill="var(--color-muted)"
            >
              {d.tick}
            </text>
          ) : null,
        )}
        <path d={area} fill="var(--color-primary)" opacity={0.1} />
        <path
          d={line}
          fill="none"
          stroke="var(--color-primary)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {hover !== null && data[hover] && (
          <g>
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={PAD.top}
              y2={PAD.top + plotH}
              stroke="var(--color-muted)"
              strokeWidth={1}
            />
            <circle
              cx={x(hover)}
              cy={y(data[hover].value)}
              r={5}
              fill="var(--color-primary)"
              stroke="var(--color-ground)"
              strokeWidth={2}
            />
          </g>
        )}
        {data.length > 0 && (
          <circle
            cx={x(data.length - 1)}
            cy={y(data[data.length - 1].value)}
            r={4}
            fill="var(--color-primary)"
            stroke="var(--color-ground)"
            strokeWidth={2}
          />
        )}
      </svg>
    </figure>
  );
}

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
