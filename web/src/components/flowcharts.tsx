// The Cash flow page's charts (ADR-027), hand-drawn SVG on the Ledger tokens like charts.tsx:
// a Sankey of one month (where the money came from and went) and a waterfall of what changed.
import { money, short } from "../money";

export type SankeyNode = {
  key: string;
  label: string;
  amount: number;
  color?: string | null;
  fixed?: boolean;
};

const NODE_W = 14;
const GAP = 6;
const MAX_NODES = 9;

/** Keep the biggest nodes and fold the rest into one "Other" node, so labels stay readable. */
export function fold(nodes: SankeyNode[], label = "Other", max = MAX_NODES): SankeyNode[] {
  const sorted = [...nodes].filter((n) => n.amount > 0).sort((a, b) => b.amount - a.amount);
  if (sorted.length <= max) return sorted;
  const kept = sorted.slice(0, max - 1);
  const rest = sorted.slice(max - 1);
  return [
    ...kept,
    { key: "other", label: `${label} (${rest.length})`, amount: rest.reduce((s, n) => s + n.amount, 0) },
  ];
}

type Placed = SankeyNode & { y: number; h: number };

const LABEL_H = 18; // a node takes at least a label's height, so small nodes never overlap

const slot = (n: SankeyNode, scale: number) => Math.max(LABEL_H, n.amount * scale);
const used = (nodes: SankeyNode[], scale: number) =>
  nodes.reduce((s, n) => s + slot(n, scale), 0) + GAP * Math.max(0, nodes.length - 1);

function place(nodes: SankeyNode[], top: number, height: number, scale: number): Placed[] {
  let y = top + Math.max(0, (height - used(nodes, scale)) / 2);
  return nodes.map((n) => {
    const h = Math.max(2, n.amount * scale);
    const room = slot(n, scale);
    const p = { ...n, y: y + (room - h) / 2, h };
    y += room + GAP;
    return p;
  });
}

function band(x0: number, y0: number, x1: number, y1: number, h0: number, h1: number) {
  const mx = (x0 + x1) / 2;
  return `M${x0},${y0} C${mx},${y0} ${mx},${y1} ${x1},${y1} L${x1},${y1 + h1} C${mx},${y1 + h1} ${mx},${y0 + h0} ${x0},${y0 + h0} Z`;
}

/** Money in on the left, the month in the middle, money out on the right. A node or band is a
 * button when onSelect is given; "left" and "right" say which side it is on. */
export function Sankey({
  left,
  right,
  middle,
  title,
  onSelect,
}: {
  left: SankeyNode[];
  right: SankeyNode[];
  middle: string;
  title: string;
  onSelect?: (side: "left" | "right", key: string) => void;
}) {
  const W = 640;
  const top = 18;
  const total = Math.max(
    1,
    left.reduce((s, n) => s + n.amount, 0),
    right.reduce((s, n) => s + n.amount, 0),
  );
  const scale = 300 / total; // the month's money is 300 units tall
  const plotH = Math.max(300, used(left, scale), used(right, scale));
  const H = plotH + top * 2;
  const xl = 170;
  const xm = W / 2 - NODE_W / 2;
  const xr = W - 180;
  const L = place(left, top, plotH, scale);
  const R = place(right, top, plotH, scale);
  const midH = Math.max(
    2,
    L.reduce((s, n) => s + n.amount * scale, 0),
    R.reduce((s, n) => s + n.amount * scale, 0),
  );
  const midY = top + (plotH - midH) / 2;
  let inY = midY;
  let outY = midY;

  const node = (side: "left" | "right", n: Placed, x: number, bandPath: string) => {
    const color = n.color ?? (side === "left" ? "var(--color-flow-in)" : "var(--color-flow-out)");
    const label = `${n.label} ${money(n.amount)}`;
    const act = onSelect && n.key !== "other" && !n.fixed ? () => onSelect(side, n.key) : undefined;
    return (
      <g
        key={`${side}-${n.key}`}
        role={act ? "button" : undefined}
        tabIndex={act ? 0 : undefined}
        aria-label={act ? `${label}: open` : label}
        className={
          act
            ? "cursor-pointer focus:outline-none [&:focus-visible>path]:opacity-60 [&:hover>path]:opacity-50"
            : undefined
        }
        onClick={act}
        onKeyDown={(e) => {
          if (act && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            act();
          }
        }}
      >
        <path d={bandPath} fill={color} opacity={0.28} />
        <rect x={x} y={n.y} width={NODE_W} height={n.h} fill={color} rx={2} />
        <text
          x={side === "left" ? x - 8 : x + NODE_W + 8}
          y={n.y + n.h / 2 + 4}
          textAnchor={side === "left" ? "end" : "start"}
          fontSize={12}
          fill="var(--color-ink)"
        >
          {n.label}{" "}
          <tspan className="num" fill="var(--color-muted)">
            {short(n.amount)}
          </tspan>
        </text>
      </g>
    );
  };

  return (
    <figure className="overflow-x-auto">
      <figcaption className="sr-only">{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full min-w-[520px]" role="group" aria-label={title}>
        {L.map((n) => {
          const h = n.amount * scale;
          const path = band(xl + NODE_W, n.y, xm, inY, n.h, h);
          inY += h;
          return node("left", n, xl, path);
        })}
        {R.map((n) => {
          const h = n.amount * scale;
          const path = band(xm + NODE_W, outY, xr, n.y, h, n.h);
          outY += h;
          return node("right", n, xr, path);
        })}
        <rect x={xm} y={midY} width={NODE_W} height={midH} fill="var(--color-ink)" rx={2} />
        <text
          x={xm + NODE_W / 2}
          y={Math.max(10, midY - 4)}
          textAnchor="middle"
          fontSize={12}
          fontWeight={600}
          fill="var(--color-ink)"
        >
          {middle}
        </text>
      </svg>
    </figure>
  );
}

export type Step = { key: string; label: string; change: number };

/** From one total to the next through the changes that made the difference. `upIsGood` colors an
 * increase as good (money in) or as a cost (money out). */
export function Waterfall({
  from,
  to,
  steps,
  labels,
  title,
  upIsGood,
}: {
  from: number;
  to: number;
  steps: Step[];
  labels: [string, string];
  title: string;
  upIsGood: boolean;
}) {
  const W = 480;
  const H = 240;
  const pad = { top: 22, bottom: 34 };
  const cols = steps.length + 2;
  const colW = W / cols;
  const barW = Math.min(64, colW - 12);
  let run = from;
  const levels = [from, to];
  for (const s of steps) {
    run += s.change;
    levels.push(run);
  }
  const max = Math.max(1, ...levels);
  const min = Math.min(0, ...levels);
  const plotH = H - pad.top - pad.bottom;
  const y = (v: number) => pad.top + plotH - ((v - min) / (max - min)) * plotH;
  const good = "var(--color-flow-in)";
  const bad = "var(--color-danger-ink)";
  let level = from;
  const bars = [
    { key: "from", label: labels[0], lo: 0, hi: from, fill: "var(--color-muted)", text: short(from) },
    ...steps.map((s) => {
      const lo = Math.min(level, level + s.change);
      const hi = Math.max(level, level + s.change);
      level += s.change;
      const up = s.change >= 0;
      return {
        key: s.key,
        label: s.label,
        lo,
        hi,
        fill: up === upIsGood ? good : bad,
        text: `${up ? "+" : "−"}${short(Math.abs(s.change))}`,
      };
    }),
    { key: "to", label: labels[1], lo: 0, hi: to, fill: "var(--color-ink)", text: short(to) },
  ];
  return (
    <figure>
      <figcaption className="sr-only">{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label={title}>
        <line x1={0} x2={W} y1={y(0)} y2={y(0)} stroke="var(--color-line)" />
        {bars.map((b, i) => {
          const x = colW * i + (colW - barW) / 2;
          const h = Math.max(1, y(b.lo) - y(b.hi));
          return (
            <g key={b.key}>
              <rect x={x} y={y(b.hi)} width={barW} height={h} rx={3} fill={b.fill} />
              <text
                x={x + barW / 2}
                y={y(b.hi) - 6}
                textAnchor="middle"
                fontSize={11}
                fill="var(--color-ink)"
                className="num"
              >
                {b.text}
              </text>
              <text x={x + barW / 2} y={H - 12} textAnchor="middle" fontSize={11} fill="var(--color-muted)">
                {b.label.length > 12 ? `${b.label.slice(0, 11)}…` : b.label}
              </text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}

export type CashSeries = {
  key: string;
  label: string;
  color: string;
  points: { day: string; balance: string }[];
  dashed?: boolean;
};

/** Cash day by day (ADR-033): the total and each account as lines, the floor dashed. */
export function CashLines({ series, floor, title }: { series: CashSeries[]; floor: number; title: string }) {
  const W = 900;
  const H = 260;
  const pad = { l: 56, r: 12, t: 12, b: 26 };
  const days = series[0]?.points.map((p) => p.day) ?? [];
  if (!days.length) return null;
  const values = series.flatMap((s) => s.points.map((p) => Number(p.balance)));
  const max = Math.max(floor, 0, ...values);
  const min = Math.min(floor, 0, ...values);
  const span = max - min || 1;
  const x = (i: number) => pad.l + (i / Math.max(1, days.length - 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + ((max - v) / span) * (H - pad.t - pad.b);
  const ticks = [max, (max + min) / 2, min];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label={title}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="var(--color-line)" />
          <text
            x={pad.l - 6}
            y={y(t) + 4}
            textAnchor="end"
            fontSize={11}
            fill="var(--color-muted)"
            className="num"
          >
            {short(t)}
          </text>
        </g>
      ))}
      {min < 0 && <line x1={pad.l} x2={W - pad.r} y1={y(0)} y2={y(0)} stroke="var(--color-muted)" />}
      {floor > 0 && (
        <line
          x1={pad.l}
          x2={W - pad.r}
          y1={y(floor)}
          y2={y(floor)}
          stroke="var(--color-danger-ink)"
          strokeDasharray="5 4"
        />
      )}
      {days.map((d, i) =>
        d.endsWith("-01") ? (
          <text key={d} x={x(i)} y={H - 6} textAnchor="middle" fontSize={11} fill="var(--color-muted)">
            {new Date(`${d}T00:00:00`).toLocaleDateString("en-US", { month: "short" })}
          </text>
        ) : null,
      )}
      {series.map((s) => (
        <polyline
          key={s.key}
          fill="none"
          stroke={s.color}
          strokeWidth={s.dashed ? 1.5 : 2.5}
          strokeDasharray={s.dashed ? "4 3" : undefined}
          points={s.points.map((p, i) => `${x(i)},${y(Number(p.balance))}`).join(" ")}
        />
      ))}
    </svg>
  );
}
