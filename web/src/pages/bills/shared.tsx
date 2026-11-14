import { type BillStatus, type Bill } from "../../api";
import { num } from "../../money";
import { EVERY } from "../Recurring";

// Bills & subscriptions (ADR-031, ADR-052): one page for what repeats. This month as one list by
// what needs attention (late, due, paid) with price changes inline; the calendar, by group, the
// year grid (editing) and the subscriptions found in the statements are the other views.

export const VIEWS = {
  month: "This month",
  calendar: "Calendar",
  group: "By group",
  grid: "Edit (year grid)",
  found: "Subscriptions",
};

export type View = keyof typeof VIEWS;

export const STATUS: Record<BillStatus, { label: string; cls: string }> = {
  paid: { label: "Paid", cls: "bg-good-bg text-good-ink" },
  due: { label: "Due", cls: "bg-surface text-ink" },
  late: { label: "Late", cls: "bg-danger-bg text-danger-ink" },
  waiting: { label: "Statement not in", cls: "bg-info-bg text-info-ink" },
  skipped: { label: "Skipped", cls: "bg-surface text-muted line-through" },
};

export const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export const isIn = (b: Bill) => b.type === "income";

export const size = (b: Bill) => Math.abs(num(b.paid ?? b.expected));

/** How often, in words: "Monthly · 7th", "Yearly", "Once", "Monthly · 16 left". */
export function repeats(b: Bill) {
  const every = EVERY[String(b.every_months)] ?? `Every ${b.every_months} months`;
  const parts = [every];
  if (b.due_day)
    parts.push(
      `${b.due_day}${["th", "st", "nd", "rd"][b.due_day % 10 > 3 || [11, 12, 13].includes(b.due_day) ? 0 : b.due_day % 10]}`,
    );
  if (b.payments_left !== null) parts.push(`${b.payments_left} left`);
  return parts.join(" · ");
}

/** The month's weeks, Monday first: day numbers, null outside the month. */
export function weeks(month: string): (number | null)[][] {
  const [y, m] = month.split("-").map(Number);
  const first = (new Date(y, m - 1, 1).getDay() + 6) % 7;
  const days = new Date(y, m, 0).getDate();
  const cells: (number | null)[] = [
    ...Array(first).fill(null),
    ...Array.from({ length: days }, (_, i) => i + 1),
  ];
  while (cells.length % 7) cells.push(null);
  return Array.from({ length: cells.length / 7 }, (_, i) => cells.slice(i * 7, i * 7 + 7));
}

export const ORDER: { status: BillStatus; title: string; hint: string }[] = [
  { status: "late", title: "Late", hint: "Past their day and not found in a statement yet." },
  {
    status: "waiting",
    title: "Waiting for the statement",
    hint: "Past their day, but the account that pays them has no statement loaded for those days yet, so the app can't tell.",
  },
  { status: "due", title: "Still to pay", hint: "Coming this month." },
  { status: "paid", title: "Paid", hint: "Matched to a statement line." },
  { status: "skipped", title: "Skipped this month", hint: "" },
];
