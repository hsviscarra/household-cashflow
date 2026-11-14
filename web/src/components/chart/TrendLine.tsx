import { type ReactNode, useState } from "react";
import { useWidth, niceTicks, PAD, Tooltip } from "./base";
import { short } from "../../money";

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
