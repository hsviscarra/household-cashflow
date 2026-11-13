import type { ExploreDimension, ExploreMeasure, ExploreResult } from "./api";
import { addMonths, money, num } from "./money";
import { asRecord } from "./prefs";

// A view on Explore (ADR-099): what to measure, the rows, the columns, a period and a filter.
// Kept by name in the person's settings; a pinned one shows on Home.

export const MEASURES: Record<ExploreMeasure, string> = {
  amount: "Amount spent",
  lines: "Number of lines",
  average: "Average line",
};
export const DIMENSIONS: Record<ExploreDimension, string> = {
  group: "Group",
  category: "Category",
  merchant: "Merchant",
  person: "Who",
  account: "Account",
  country: "Country",
  kind: "Fixed or variable",
  month: "Month",
  year: "Year",
};
export const PERIODS = {
  "3": "Last 3 months",
  "6": "Last 6 months",
  "12": "Last 12 months",
  "24": "Last 24 months",
  ytd: "This year",
  last_year: "Last year",
};
export type Period = keyof typeof PERIODS;
export type ViewSpec = {
  measure: ExploreMeasure;
  rows: ExploreDimension;
  cols: ExploreDimension | "none";
  period: Period;
  person: "Both" | "Hernan" | "Lauren" | "Joint";
  group_id: number | null;
  show: "table" | "chart";
};
export type SavedView = { name: string; spec: ViewSpec; pinned: boolean };
export const DEFAULT_VIEW: ViewSpec = {
  measure: "amount",
  rows: "group",
  cols: "month",
  period: "6",
  person: "Both",
  group_id: null,
  show: "table",
};
export const VIEWS_KEY = "explore:views";
export const MAX_VIEWS = 20;
const PEOPLE = ["Both", "Hernan", "Lauren", "Joint"];

/** A spec read back from settings, with anything unknown replaced by the default. */
export function viewSpec(saved: unknown): ViewSpec {
  const s = asRecord(saved);
  const rows = (s.rows as string) in DIMENSIONS ? (s.rows as ExploreDimension) : DEFAULT_VIEW.rows;
  const asked =
    s.cols === "none" || (s.cols as string) in DIMENSIONS ? (s.cols as ViewSpec["cols"]) : DEFAULT_VIEW.cols;
  const cols = asked === rows ? "none" : asked; // rows and columns can't be the same
  return {
    measure: (s.measure as string) in MEASURES ? (s.measure as ExploreMeasure) : DEFAULT_VIEW.measure,
    rows,
    cols,
    period: (s.period as string) in PERIODS ? (s.period as Period) : DEFAULT_VIEW.period,
    person: PEOPLE.includes(s.person as string) ? (s.person as ViewSpec["person"]) : "Both",
    group_id: typeof s.group_id === "number" ? s.group_id : null,
    show: s.show === "chart" ? "chart" : "table",
  };
}

export function savedViews(value: unknown): SavedView[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((x) => typeof x === "object" && x !== null && typeof x.name === "string")
    .map((x) => ({ name: x.name as string, spec: viewSpec(x.spec), pinned: x.pinned === true }));
}

/** The first and last month of a period, counted from the month of `today`. */
export function monthsOf(period: Period, today: string): { start: string; end: string } {
  const now = `${today.slice(0, 7)}-01`;
  const year = Number(today.slice(0, 4));
  if (period === "ytd") return { start: `${year}-01-01`, end: now };
  if (period === "last_year") return { start: `${year - 1}-01-01`, end: `${year - 1}-12-01` };
  return { start: addMonths(now, -(Number(period) - 1)), end: now };
}

/** What the server is asked for. */
export function request(spec: ViewSpec, today: string) {
  return {
    ...monthsOf(spec.period, today),
    rows: spec.rows,
    cols: spec.cols === "none" ? undefined : spec.cols,
    measure: spec.measure,
    person: spec.person === "Both" ? undefined : spec.person,
    group_id: spec.group_id ?? undefined,
  };
}

/** A cell as text: money for amounts and averages, a whole number for lines. */
export const cellText = (measure: ExploreMeasure, v: string | number) =>
  measure === "lines" ? String(Math.round(num(v))) : money(v);

/** The table as CSV, with its totals. */
export function exploreCsv(r: ExploreResult): string {
  const cell = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const number = (v: string) => (r.measure === "lines" ? String(Math.round(num(v))) : num(v).toFixed(2));
  const wide = r.cols.length > 0;
  const head = [DIMENSIONS[r.rows_by], ...r.cols, wide ? "Total" : MEASURES[r.measure]];
  const body = r.rows.map((name, i) => [
    name,
    ...(wide ? r.cells[i].map(number) : []),
    number(r.row_totals[i]),
  ]);
  const foot = ["Total", ...r.col_totals.map(number), number(r.total)];
  return [head, ...body, foot].map((row) => row.map(cell).join(",")).join("\n");
}
