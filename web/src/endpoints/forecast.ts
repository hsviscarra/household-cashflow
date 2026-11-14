import { query } from "./months";
import { send } from "./settings";

// ---------------- F15: projections ----------------
export type ProjectionEvent = {
  day: string;
  name: string;
  amount: string;
  kind: "income" | "fixed" | "purchase" | "variable" | "change";
  account_id?: number | null;
};

export type ProjectionMonth = {
  month: string;
  income: string;
  fixed: string;
  variable: string;
  purchases: string;
  net: string;
  end_cash: string;
  items: ProjectionEvent[];
  // ADR-096: where cash likely ends, and the groups that make the month heavier than usual.
  end_cash_low?: string | null;
  end_cash_high?: string | null;
  seasonal?: { group_name: string; extra: string }[];
};

export type Projection = {
  today: string;
  start_cash: string;
  cash_as_of: string | null;
  variable_per_month: string;
  average_months: string[];
  months: ProjectionMonth[];
  daily: { day: string; balance: string }[];
  lowest: { day: string; balance: string } | null;
  next_payday: ProjectionEvent | null;
  alerts: {
    month: string;
    group_id: number;
    group_name: string;
    amount: string;
    average: string;
    change: string | null;
  }[];
  // ADR-033 (optional so older answers and tests still fit)
  horizon?: number;
  average_over?: number;
  floor?: string;
  held?: string;
  include_held?: boolean;
  accounts?: AccountRun[];
  first_short?: string | null;
  end_cash?: string;
  base?: {
    lowest: { day: string; balance: string } | null;
    first_short: string | null;
    end_cash: string;
  } | null;
  // ADR-096: the likely range day by day and the chance of going under the floor.
  band?: { day: string; low: string; high: string }[];
  chance_under_floor?: string | null;
  seasons?: boolean;
  seasonal_groups?: number;
  seasons_from?: "groups" | "all" | null; // each group's own year, or all spending together
};

// ADR-033: choices, per-account runs and what-ifs.
export type ForecastOptions = {
  horizon: number;
  average_over: number;
  floor: number;
  include_held: boolean;
  seasons: boolean; // everyday spending follows the seasons (ADR-096)
};

export type ForecastChange = {
  name: string;
  amount: string; // money in positive
  every: "month" | "once";
  day?: number;
  on?: string | null;
  account_id?: number | null;
};

export type AccountRun = {
  account_id: number;
  name: string;
  start: string;
  as_of: string | null;
  daily: { day: string; balance: string }[];
  lowest: { day: string; balance: string };
  under_floor: string | null;
  move: string;
};

export const DEFAULT_FORECAST: ForecastOptions = {
  horizon: 3,
  average_over: 3,
  floor: 0,
  include_held: false,
  seasons: true,
};

export const fetchProjection = (o: ForecastOptions = DEFAULT_FORECAST) => {
  const same = (Object.keys(DEFAULT_FORECAST) as (keyof ForecastOptions)[]).every(
    (k) => o[k] === DEFAULT_FORECAST[k],
  );
  return send<Projection>(
    "GET",
    `/api/projections${same ? "" : query({ horizon: o.horizon, average_over: o.average_over, floor: o.floor, include_held: String(o.include_held), seasons: String(o.seasons) })}`,
  );
};

export const runScenario = (o: ForecastOptions, changes: ForecastChange[]) =>
  send<Projection>("POST", "/api/projections/scenario", { ...o, changes });

// ---------- the month in ten answers (ADR-033) ----------
export type MonthAnswer = {
  n: number;
  question: string;
  answer: string;
  detail: string;
  tone: "good" | "warn" | "neutral";
  link: string | null;
};

export const fetchAnswers = (month: string) => send<MonthAnswer[]>("GET", `/api/reports/${month}/answers`);

// ---------- F16: monthly report and export ----------
export type Tone = "good" | "bad" | "neutral";

export type Finding = { title: string; text: string; tone: Tone };

export type ReportFlow = {
  income: string;
  expenses: string;
  savings: string;
  debt_payments: string;
  net: string;
  savings_rate: string | null;
};

export type ReportFacts = {
  month: string;
  data: { complete: boolean; source?: string; open: string[] };
  cash_flow: { month: ReportFlow | null; last_month: ReportFlow | null; average_3_months: ReportFlow | null };
  [key: string]: unknown;
};

export type MonthlyReport = {
  month: string;
  written_by: "claude" | "rules";
  model: string | null;
  generated_at: string | null;
  generated_by: string;
  facts: ReportFacts;
  findings: Finding[];
  notice: string | null;
};

export type ExportDataset = { key: string; title: string; by: "month" | "year" };

export const fetchReportMonths = () => send<{ months: string[]; claude: boolean }>("GET", "/api/reports");

export const fetchReport = (month: string) => send<MonthlyReport | null>("GET", `/api/reports/${month}`);

export const generateReport = (month: string) =>
  send<MonthlyReport>("POST", `/api/reports/${month}/generate`);

export const fetchExports = () => send<ExportDataset[]>("GET", "/api/exports");

/** A download link: the month for monthly data, its year for yearly views. */
export const exportUrl = (
  key: string,
  fmt: "csv" | "xlsx",
  period: { month?: string; year?: number } = {},
) => {
  const q = new URLSearchParams();
  if (period.month) q.set("month", period.month);
  if (period.year) q.set("year", String(period.year));
  const qs = q.toString();
  return `/api/exports/${key}.${fmt}${qs ? `?${qs}` : ""}`;
};

// ---------- F17: backups ----------
export type BackupStatus = {
  where: "azure" | "local";
  backup: {
    file: string;
    finished_at: string;
    size: number;
    migration: string | null;
    rows: number;
    seconds: number | null;
  } | null;
  drill: { ok: boolean; finished_at: string; backup?: string; problems?: string[]; rows?: number } | null;
  backup_overdue: boolean;
  drill_overdue: boolean;
  error: string | null;
};

export const fetchBackups = () => send<BackupStatus>("GET", "/api/backups");

// ---------- F19: statements from a chosen month ----------
export type GroupGap = { group: string; workbook: string; statements: string; difference: string };

export type SourceMonth = {
  month: string;
  workbook_income: string;
  statements_income: string;
  workbook_spending: string;
  statements_spending: string;
  statement_lines: number;
  groups: GroupGap[];
};

export type Sources = {
  statements_from: string | null;
  workbook_first: string | null;
  workbook_last: string | null;
  check: SourceMonth[];
};

export const fetchSources = () => send<Sources>("GET", "/api/sources");

export const saveSources = (statements_from: string | null) =>
  send<Sources>("PUT", "/api/sources", { statements_from });
