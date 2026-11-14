import { type HoldingClass, type BalanceSheet, type SheetItem } from "../../api";
import { localToday, num, money } from "../../money";
import { useQueryClient } from "@tanstack/react-query";

export type Notify = (message: string, tone?: "good" | "bad") => void;

export const CLASSES: {
  id: HoldingClass;
  label: string;
  side: "asset" | "liability" | null;
  group: string;
}[] = [
  { id: "property", label: "Property", side: "asset", group: "Property" },
  { id: "vehicle", label: "Vehicle", side: "asset", group: "Vehicles" },
  { id: "investment", label: "Investment", side: "asset", group: "Investments" },
  { id: "cash", label: "Cash or savings", side: "asset", group: "Cash" },
  {
    id: "purchase",
    label: "Purchase in progress (down payment)",
    side: "asset",
    group: "Purchases in progress",
  },
  { id: "loan", label: "Loan", side: "liability", group: "Loans" },
  { id: "card", label: "Credit card", side: "liability", group: "Credit cards" },
  {
    id: "personal_loan",
    label: "Money owed to or held for a person",
    side: "liability",
    group: "Held for or owed to people",
  },
  { id: "other", label: "Other", side: null, group: "Other" },
];

export const SOURCE: Record<string, string> = {
  statement: "latest statement",
  bank_sync: "bank sync",
  excel: "Cash Flow sheet",
  manual: "entered here",
  lines: "payments in its category",
  amortization: "amortization table",
};

export const today = () => localToday();

export const day = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

/** "Net worth 175,193.31: you own 233,006.95 and owe 57,813.64." */
export function sheetHeadline(s: BalanceSheet): string {
  if (!s.items.length) return "Debt & Net Worth";
  const net = num(s.net_worth);
  return `Net worth ${net < 0 ? "−" : ""}${money(Math.abs(net))}: you own ${money(s.assets)} and owe ${money(s.liabilities)}`;
}

export function useRefresh() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["networth"] });
}

// How long a value stays fresh (ADR-032), by kind: bank and card balances come with each
// statement, investments daily, property and vehicles once a year. Money held for a person moves
// with their lines, so it never goes out of date.
export const FRESH_DAYS: Partial<Record<HoldingClass, number>> = {
  cash: 45,
  card: 45,
  loan: 45,
  purchase: 45,
  investment: 10,
  property: 365,
  vehicle: 365,
  other: 180,
};

export const daysBetween = (a: string, b: string) =>
  Math.round((new Date(`${b}T00:00:00`).getTime() - new Date(`${a}T00:00:00`).getTime()) / 86_400_000);

/** Whether an item's value is out of date, and how old it is. */
export function freshness(item: SheetItem, on: string): { stale: boolean; age: number | null } {
  const limit = FRESH_DAYS[item.holding_class];
  if (!item.as_of) return { stale: limit !== undefined, age: null };
  const age = daysBetween(item.as_of, on);
  return { stale: limit !== undefined && age > limit, age };
}

/** An old workbook value next to a fresh one of the same kind is probably the same money twice. */
export function maybeDuplicate(item: SheetItem, items: SheetItem[], on: string): string | null {
  if (item.source !== "excel" || !freshness(item, on).stale) return null;
  const twin = items.find(
    (i) =>
      i.key !== item.key && i.is_active && i.holding_class === item.holding_class && i.source !== "excel",
  );
  return twin ? twin.name : null;
}

/** Monthly debt payments: loans' payments and purchases' installments. */
export function monthlyDebt(items: SheetItem[]): number {
  return items
    .filter((i) => i.is_active)
    .reduce((s, i) => s + num(i.loan?.monthly_payment ?? 0) + num(i.purchase?.installment ?? 0), 0);
}

/** Paying `extra` more each month on a loan: how many months sooner it ends and the interest
 * saved. The rate comes from the schedule (balance, interest left, months left). */
export function whatIf(
  s: { balance: string | null; interest_left: string; left: number },
  extra: number,
): { months: number; sooner: number; saved: number } | null {
  const balance = num(s.balance);
  const n = s.left;
  if (!balance || n <= 0 || extra <= 0) return null;
  const pay = (balance + num(s.interest_left)) / n; // principal and interest a month
  // The monthly rate r with pay = balance·r / (1 − (1+r)^−n), by bisection.
  let lo = 0;
  let hi = 0.05;
  for (let k = 0; k < 80; k++) {
    const r = (lo + hi) / 2;
    const p = r === 0 ? balance / n : (balance * r) / (1 - (1 + r) ** -n);
    if (p > pay) hi = r;
    else lo = r;
  }
  const r = (lo + hi) / 2;
  const total = pay + extra;
  const months =
    r === 0 ? Math.ceil(balance / total) : Math.ceil(-Math.log(1 - (r * balance) / total) / Math.log(1 + r));
  return {
    months,
    sooner: n - months,
    saved: Math.max(0, num(s.interest_left) - (months * total - balance)),
  };
}
