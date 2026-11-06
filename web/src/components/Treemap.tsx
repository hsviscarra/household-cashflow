// A squarified treemap (ADR-028): block size = amount, each block a button that goes inside.
import { money } from "../money";

export type TreeItem = { key: string; label: string; amount: number; color?: string | null; note?: string };
export type Rect = { x: number; y: number; w: number; h: number };

const worst = (row: number[], side: number) => {
  const sum = row.reduce((s, v) => s + v, 0);
  const max = Math.max(...row);
  const min = Math.min(...row);
  return Math.max((side * side * max) / (sum * sum), (sum * sum) / (side * side * min));
};

/** Lay out areas (already scaled to the box) in rows that keep blocks close to square. */
export function squarify(values: number[], box: Rect): Rect[] {
  let rest = values.map((v, i) => ({ v, i }));
  let { x, y, w, h } = box;
  const result: Rect[] = new Array(values.length);
  while (rest.length) {
    const side = Math.min(w, h);
    const row: { v: number; i: number }[] = [];
    while (rest.length) {
      const next = [...row.map((r) => r.v), rest[0].v];
      if (
        row.length &&
        worst(next, side) >
          worst(
            row.map((r) => r.v),
            side,
          )
      )
        break;
      row.push(rest[0]);
      rest = rest.slice(1);
    }
    const sum = row.reduce((s, r) => s + r.v, 0);
    if (w >= h) {
      const cw = sum / h;
      let cy = y;
      for (const r of row) {
        const ch = r.v / cw;
        result[r.i] = { x, y: cy, w: cw, h: ch };
        cy += ch;
      }
      x += cw;
      w -= cw;
    } else {
      const ch = sum / w;
      let cx = x;
      for (const r of row) {
        const rw = r.v / ch;
        result[r.i] = { x: cx, y, w: rw, h: ch };
        cx += rw;
      }
      y += ch;
      h -= ch;
    }
  }
  return result;
}

/** Blocks in percent of the box, biggest first; items at zero or below are left out. */
export function layout(items: TreeItem[], aspect = 2.4): (TreeItem & Rect)[] {
  const shown = items.filter((i) => i.amount > 0).sort((a, b) => b.amount - a.amount);
  const total = shown.reduce((s, i) => s + i.amount, 0);
  if (!total) return [];
  // Square in the box as drawn (about 2.4 times wider than tall), then in percent of it.
  const w = 100 * aspect;
  const rects = squarify(
    shown.map((i) => (i.amount / total) * w * 100),
    { x: 0, y: 0, w, h: 100 },
  );
  return shown.map((i, k) => ({
    ...i,
    x: (rects[k].x / w) * 100,
    y: rects[k].y,
    w: (rects[k].w / w) * 100,
    h: rects[k].h,
  }));
}

export default function Treemap({
  items,
  title,
  onSelect,
}: {
  items: TreeItem[];
  title: string;
  onSelect?: (key: string) => void;
}) {
  const blocks = layout(items);
  if (!blocks.length) return <p className="text-muted">Nothing to show.</p>;
  return (
    <div role="group" aria-label={title} className="relative h-80 w-full overflow-hidden rounded-xl md:h-96">
      {blocks.map((b) => {
        const small = b.w < 8 || b.h < 12;
        return (
          <button
            key={b.key}
            type="button"
            title={`${b.label}: ${money(b.amount)}`}
            aria-label={`${b.label} ${money(b.amount)}${b.note ? `, ${b.note}` : ""}`}
            onClick={() => onSelect?.(b.key)}
            className="absolute flex flex-col items-start justify-start overflow-hidden border-2 border-ground p-2 text-left text-white hover:brightness-110 focus-visible:z-10 focus-visible:outline-3 focus-visible:outline-primary"
            style={{
              left: `${b.x}%`,
              top: `${b.y}%`,
              width: `${b.w}%`,
              height: `${b.h}%`,
              background: b.color ?? "var(--color-flow-out)",
              borderRadius: 10,
            }}
          >
            {!small && (
              <>
                <span className="text-sm font-semibold leading-tight">{b.label}</span>
                <span className="num text-xs opacity-90">{money(b.amount)}</span>
                {b.note && b.h > 22 && <span className="text-xs opacity-80">{b.note}</span>}
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}
