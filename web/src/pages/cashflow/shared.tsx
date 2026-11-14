import { type Flow, type FlowFilter } from "../../api";
import { num } from "../../money";
import { type Step } from "../../components/flowcharts";

// The Cash flow page (ADR-027): twelve months of money in and out, one month as a Sankey, a
// drill-down from a band to its group, categories, merchants and lines, and why the month
// changed from the one before. The year history (the old Overview) follows below.

export const MAX_STEPS = 5;

export const PEOPLE_NAMES = ["Hernan", "Lauren", "Joint"];

/** A row of the month: money in by category; money out by group, savings and payments by
 * category (they read better by what they are: Investing, Card Payment). */
export type Row = {
  key: string;
  label: string;
  side: "in" | "out";
  amount: number;
  prev: number;
  color: string | null;
};

export function rows(flows: Flow[]): Row[] {
  const out = new Map<string, Row>();
  for (const f of flows) {
    const side = f.type === "income" ? "in" : "out";
    const byCategory = side === "in" || f.type === "savings" || f.type === "debt_payment";
    const key = `${side}:${byCategory ? `c${f.category_id}` : `g${f.group_id}`}`;
    // "Salary Hernan" rather than "Hernan"; "Office rent" says enough on its own.
    const label = byCategory
      ? PEOPLE_NAMES.includes(f.category_name)
        ? `${f.group_name} ${f.category_name}`
        : f.category_name
      : f.group_name;
    const row = out.get(key) ?? { key, label, side, amount: 0, prev: 0, color: f.group_color };
    row.amount += num(f.amount);
    row.prev += num(f.prev);
    out.set(key, row);
  }
  return [...out.values()];
}

/** What a row opens: its group, or its category. */
export function drillOf(key: string): FlowFilter & { group?: number; category?: number } {
  const [side, id] = key.split(":");
  const n = Number(id.slice(1));
  return id.startsWith("g")
    ? { side: side as "in" | "out", group: n }
    : { side: side as "in" | "out", category: n };
}

/** The biggest changes from the month before, the rest folded into "Everything else". */
export function steps(list: Row[], max = MAX_STEPS): Step[] {
  const changed = list
    .map((r) => ({ key: r.key, label: r.label, change: r.amount - r.prev }))
    .filter((s) => Math.abs(s.change) >= 0.005)
    .sort((a, b) => Math.abs(b.change) - Math.abs(a.change));
  if (changed.length <= max) return changed;
  const rest = changed.slice(max - 1).reduce((s, c) => s + c.change, 0);
  return [...changed.slice(0, max - 1), { key: "rest", label: "Everything else", change: rest }];
}
