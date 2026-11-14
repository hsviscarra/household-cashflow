import { type Money } from "./history";
import { type Txn } from "./imports";
import { type Owner, send } from "./settings";

// ---------------- F11: recurring entries ----------------
export type TemplateType = "income" | "expense" | "savings" | "transfer" | "debt_payment" | "fee_interest";

export type RecurringTemplate = {
  template_id: number;
  name: string;
  category_id: number;
  category_path: string | null;
  type: TemplateType;
  amount: string | null;
  amounts: { from_month: string; amount: string }[];
  start_month: string;
  end_month: string | null;
  account_id: number | null;
  account_name: string | null;
  person: string | null;
  match_pattern: string | null;
  tolerance_pct: string;
  is_active: boolean;
  sort_order: number;
  source: "manual" | "excel";
  group: string;
  notes: string | null;
  every_months: number; // ADR-031: 1 monthly, 2-12 months, 0 once
  due_day: number | null;
};

export type TemplateInput = {
  name: string;
  category_id: number;
  type: TemplateType;
  amount: string;
  start_month: string;
  end_month?: string | null;
  account_id?: number | null;
  person?: string | null;
  match_pattern?: string | null;
  tolerance_pct?: string;
  notes?: string | null;
  every_months?: number;
  due_day?: number | null;
};

export type TemplatePatch = Partial<Omit<TemplateInput, "amount" | "start_month">> & {
  is_active?: boolean;
  sort_order?: number;
};

export type CellStatus = "matched" | "planned" | "skipped" | "not_generated" | "none";

export type GridCell = {
  month: string;
  entry_id: number | null;
  expected: string | null;
  actual: string | null;
  lines: number;
  status: CellStatus;
  is_override: boolean;
  notes: string | null;
};

export type GridRow = {
  template_id: number;
  name: string;
  type: TemplateType;
  group: string;
  category_path: string | null;
  is_active: boolean;
  cells: GridCell[];
};

export type RecurringGrid = { year: number; months: string[]; excel_months: string[]; rows: GridRow[] };

export type RecurringEntry = {
  entry_id: number;
  template_id: number;
  template_name: string;
  month: string;
  amount: string;
  template_amount: string | null;
  is_override: boolean;
  status: "planned" | "skipped";
  notes: string | null;
  tolerance: string;
  lines: Txn[];
  candidates: Txn[];
};

export type ExcelRow = {
  name: string;
  group: string | null;
  label: string;
  block: string;
  category_id: number | null;
  category_path: string | null;
  type: string | null;
  months: number;
  latest: string;
  suggested: boolean;
  exists: boolean;
};

export const fetchRecurringGrid = (year: number) =>
  send<RecurringGrid>("GET", `/api/recurring/grid?year=${year}`);

export const fetchTemplates = () => send<RecurringTemplate[]>("GET", "/api/recurring/templates");

export type FoundBill = {
  merchant: string;
  every_months: number;
  amount: Money;
  category_id: number;
  category_path: string | null;
  account_id: number | null;
  account_name: string | null;
  person: Owner | null;
  match_pattern: string | null;
  due_day: number;
  times: number;
  last_date: string;
  next_expected: string | null;
  examples: string[];
};

export const fetchFoundBills = () => send<FoundBill[]>("GET", "/api/recurring/found");

export const createTemplate = (t: TemplateInput) =>
  send<RecurringTemplate>("POST", "/api/recurring/templates", t);

export const updateTemplate = (id: number, t: TemplatePatch) =>
  send<RecurringTemplate>("PATCH", `/api/recurring/templates/${id}`, t);

export const deleteTemplate = (id: number) => send<void>("DELETE", `/api/recurring/templates/${id}`);

export const changeTemplateAmount = (id: number, from_month: string, amount: string) =>
  send<{ count: number }>("POST", `/api/recurring/templates/${id}/amount`, { from_month, amount });

export const generateMonth = (month: string) =>
  send<{ count: number }>("POST", "/api/recurring/generate", { month });

export const copyMonth = (b: {
  from_month: string;
  to_start: string;
  to_end: string;
  template_ids?: number[];
}) => send<{ count: number }>("POST", "/api/recurring/copy", b);

export const matchRecurring = () => send<{ count: number }>("POST", "/api/recurring/match");

export const fetchEntry = (id: number) => send<RecurringEntry>("GET", `/api/recurring/entries/${id}`);

export const editEntry = (
  id: number,
  b: { amount?: string; reset?: boolean; status?: "planned" | "skipped"; notes?: string },
) => send<RecurringEntry>("PATCH", `/api/recurring/entries/${id}`, b);

export const linkLine = (entryId: number, transaction_id: number) =>
  send<RecurringEntry>("POST", `/api/recurring/entries/${entryId}/lines`, { transaction_id });

export const unlinkLine = (transactionId: number) =>
  send<void>("DELETE", `/api/recurring/lines/${transactionId}`);

export const fetchExcelRows = (year: number) =>
  send<ExcelRow[]>("GET", `/api/recurring/excel-rows?year=${year}`);

export const createFromExcel = (year: number, names: string[]) =>
  send<{ templates: number; entries: number; linked: number }>("POST", "/api/recurring/from-excel", {
    year,
    names,
  });

// ---------------- F12: month status ----------------
export type StatusItem = {
  kind: "statement" | "import" | "uncategorized" | "transfer" | "recurring" | "balance" | "note";
  text: string;
  link: string;
  count: number;
};

export type MonthCoverage = {
  account_id: number;
  state: "full" | "partial" | "none";
  covered_days: number;
  days: number;
};

export type MonthStatus = {
  month: string;
  source: "excel" | "statements";
  complete: boolean;
  items: StatusItem[];
  coverage: MonthCoverage[];
};

export type DataStatus = {
  today: string;
  excel_through: string | null;
  accounts: { account_id: number; name: string; kind: string; owner: string }[];
  months: MonthStatus[];
  loads: { loaded_at: string; source: string; file_name: string | null; rows: number; loaded_by: string }[];
  statements?: AccountTimeline[];
  sources?: AccountSource[];
  script?: { state: "ok" | "silent" | "never"; last_seen: string | null; note: string } | null;
};

/** How an account's data arrives and where it stands today (ADR-072). */
export type AccountSource = {
  account_id: number;
  name: string;
  how: "bank_sync" | "email" | "upload";
  last_day: string | null;
  state: "up_to_date" | "on_its_way" | "on_import" | "you_upload" | "late";
  note: string;
  expected?: string | null;
};

export type TimelineStatement = {
  statement_file_id: number;
  file_name: string;
  start: string;
  end: string;
  state: "loaded" | "waiting" | "problems" | "not_read" | "synced";
  batch_id: number | null;
};

// due: the current cycle, whose statement the bank issues around that day (not missing).
export type StatementGap = {
  start: string;
  end: string;
  due: string | null;
  closes?: string[]; // the statements that fill it, by closing day
  files?: string[]; // their usual file names, for banks that date them
};

export type AccountTimeline = {
  account_id: number;
  name: string;
  closed_on: string | null;
  opened_on?: string | null;
  start_day: number | null;
  statements: TimelineStatement[];
  gaps: StatementGap[];
};

export const fetchStatus = () => send<DataStatus>("GET", "/api/status");
