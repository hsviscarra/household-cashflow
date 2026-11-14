import { ApiError, send } from "./settings";

// ---------- history and cash flow (F2) ----------
// Money arrives as decimal strings; convert only for display and charts.
export type Money = string;

export type MonthlyCashflow = {
  cash_month: string;
  income: Money;
  expenses: Money;
  card_payments?: Money; // cash view only (F10)
  savings: Money;
  debt_payments: Money;
  net: Money;
  cumulative_net: Money;
  savings_rate: string | null;
  transactions: number;
};

export type CategoryMonth = {
  cash_month: string;
  type: string;
  group_id: number;
  group_name: string;
  group_color: string | null;
  category_id: number;
  category_name: string;
  amount: Money;
  transactions: number;
};

export type PlanMonth = { month: string; income: Money; outflows: Money };

export type MonthCheck = {
  month: string;
  sheet: string;
  income_rows: Money;
  income_workbook: Money | null;
  expense_rows: Money;
  expense_workbook: Money | null;
  left_out: string[];
  typed_total: boolean;
  explained: boolean;
};

export type MappingReview = {
  block: string;
  group: string | null;
  label: string;
  type: string;
  category: string;
  person: string | null;
  months: number;
  total: Money;
  review: string | null;
};

export type HistoryPreview = {
  file_name: string;
  file_sha256: string;
  already_loaded: boolean;
  first_month: string | null;
  last_month: string | null;
  months: number;
  actual_rows: number;
  plan_rows: number;
  plan_months: string[];
  years: { year: number; months: number; income: Money; outflows: Money }[];
  mismatches: MonthCheck[];
  unmapped: { sheet: string; cell: string; label: string; value: Money }[];
  mapping: MappingReview[];
  snapshots: { as_of: string; name: string; kind: string; amount: Money; notes: string }[];
  side_cells: number;
};

export type HistoryLoad = {
  load_id: number;
  transactions: number;
  budget_rows: number;
  snapshots: number;
  raw_cells: number;
  replaced_transactions: number;
};

export async function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(path, { method: "POST", body: form, headers: { Accept: "application/json" } });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail;
    throw new ApiError(typeof detail === "string" ? detail : `Upload failed (${resp.status}).`, resp.status);
  }
  return data as T;
}

export type CashView = "spending" | "cash";

export const fetchMonthly = (view: CashView = "spending") =>
  send<MonthlyCashflow[]>("GET", `/api/cashflow/monthly${view === "cash" ? "?view=cash" : ""}`);

export const fetchCategoryMonths = (year: number) =>
  send<CategoryMonth[]>("GET", `/api/cashflow/categories?year=${year}`);

export const fetchPlan = () => send<PlanMonth[]>("GET", "/api/cashflow/plan");

export const previewHistory = (file: File) => upload<HistoryPreview>("/api/history/excel/preview", file);

export const loadHistory = (file: File) => upload<HistoryLoad>("/api/history/excel/load", file);

// ---------- statements (F3) ----------
export type Statement = {
  statement_file_id: number;
  file_name: string;
  source: string;
  source_label: string;
  status: "detected" | "needs_account" | "unknown_format";
  accounts: { account_id: number; name: string; last4: string | null }[];
  account_match: "last4" | "by_bank" | "owner" | "manual" | null;
  last4_found: string[];
  period_start: string | null;
  period_end: string | null;
  page_count: number;
  size_bytes: number;
  uploaded_by: string;
  uploaded_at: string;
  can_read: boolean;
  batch: { batch_id: number; status: "preview" | "approved" | "rejected"; tieout_ok: boolean } | null;
};

export type UploadResult = {
  file_name: string;
  outcome: "stored" | "duplicate" | "rejected";
  message: string;
  statement: Statement | null;
};

export async function uploadStatements(files: File[]): Promise<UploadResult[]> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const resp = await fetch("/api/statements", {
    method: "POST",
    body: form,
    headers: { Accept: "application/json" },
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail;
    throw new ApiError(typeof detail === "string" ? detail : `Upload failed (${resp.status}).`, resp.status);
  }
  return data as UploadResult[];
}

export const fetchStatements = () => send<Statement[]>("GET", "/api/statements");

export const assignStatement = (id: number, account_ids: number[]) =>
  send<Statement>("PATCH", `/api/statements/${id}`, { account_ids });

export const statementFileUrl = (id: number) => `/api/statements/${id}/file`;
