import { type TemplateType, type GridCell, type GridRow } from "../../api";
import { localToday, num } from "../../money";
import { useQueryClient } from "@tanstack/react-query";

export type Notify = (message: string, tone?: "good" | "bad") => void;

export type Selected =
  { kind: "cell"; template: number; month: string } | { kind: "template"; template: number } | null;

export const TYPES: { id: TemplateType; label: string }[] = [
  { id: "expense", label: "Expense" },
  { id: "income", label: "Income" },
  { id: "debt_payment", label: "Loan or card payment" },
  { id: "savings", label: "Savings or investing" },
  { id: "transfer", label: "Transfer" },
  { id: "fee_interest", label: "Fees and interest" },
];

export const isIncome = (t: string) => t === "income";

/** How often an item repeats (ADR-031). */
export const EVERY: Record<string, string> = {
  "1": "Monthly",
  "2": "Every 2 months",
  "3": "Every 3 months",
  "4": "Every 4 months",
  "6": "Every 6 months",
  "12": "Yearly",
  "0": "Once",
};

export const thisMonth = () => localToday().slice(0, 7);

export const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });

/** What a cell counts as: the matched lines, else the expected amount; skipped months count 0. */
export function cellValue(c: GridCell): number {
  if (c.status === "matched") return num(c.actual);
  if (c.status === "planned") return num(c.expected);
  return 0;
}

/** Monthly totals of the grid: money in, money out (positive) and what is left. */
export function totals(rows: GridRow[]) {
  const n = rows[0]?.cells.length ?? 12;
  const income = Array<number>(n).fill(0);
  const out = Array<number>(n).fill(0);
  for (const r of rows)
    r.cells.forEach((c, i) => {
      const v = cellValue(c);
      if (v > 0) income[i] += v;
      else out[i] -= v;
    });
  return { income, out, left: income.map((v, i) => v - out[i]) };
}

export function useRefresh() {
  const qc = useQueryClient();
  return () =>
    ["recurring", "transactions", "cashflow"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
}

// ---------------------------------------------------------------- templates
export type Account = { account_id: number; name: string };
