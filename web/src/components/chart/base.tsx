import { useRef, useState, useEffect, type ReactNode } from "react";

// Hand-drawn SVG charts on the Mercado tokens: they follow light and dark mode through CSS
// variables and need no chart library. Specs (docs/design-system.md, Charts): columns at most
// 24px wide with 4px rounded tops, 2px gaps, 2px lines, hairline solid grid, legend always shown.

export function useWidth<T extends HTMLElement>(fallback = 640) {
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

export function topRounded(x: number, y: number, w: number, h: number, r = 4) {
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

export function Tooltip({ x, width, children }: { x: number; width: number; children: ReactNode }) {
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

export const IN = "var(--color-flow-in)";

export const OUT = "var(--color-flow-out)";

export const PAD = { top: 12, right: 8, bottom: 28, left: 44 };
