import { pct, money } from "../../money";
import { type ReactNode } from "react";

// Groceries → Trends (ADR-067): a year of supermarket spending by aisle, any two months side by
// side by aisle, type or brand, and the patterns in it: trips and basket, shopping days, prices
// that moved, new products and regulars not bought this month.

export const SHOWN = 7;

// aisles with their own color; the rest share one
export const OTHER = "Everything else";

export const COLORS = [
  "var(--color-cat-groceries)",
  "var(--color-cat-transport)",
  "var(--color-cat-dining)",
  "var(--color-cat-services)",
  "var(--color-cat-delivery)",
  "var(--color-cat-shopping)",
  "var(--color-cat-health)",
];

export const OTHER_COLOR = "var(--color-cat-fixed)";

export const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export const LONG_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export type Dim = "aisle" | "type" | "brand";

export const DIMS: [Dim, string][] = [
  ["aisle", "Aisle"],
  ["type", "Type of product"],
  ["brand", "Brand"],
];

export const NO_LABEL: Record<Dim, string> = {
  aisle: "Not grouped yet",
  type: "No type yet",
  brand: "No brand yet",
};

export const signedPct = (v: number) => `${v > 0 ? "+" : ""}${pct(v)}`;

export const round = (v: string | number) => money(v).replace(/\.\d\d$/, "");

export function Tile({ label, value, children }: { label: string; value: string; children: ReactNode }) {
  return (
    <div className="card p-5">
      <p className="label">{label}</p>
      <p className="num mt-1 font-display text-3xl font-bold">{value}</p>
      <p className="mt-1 text-sm text-muted">{children}</p>
    </div>
  );
}
