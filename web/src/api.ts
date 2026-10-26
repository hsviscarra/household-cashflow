export type Health = {
  status: "ok" | "degraded";
  version: string;
  git_sha: string;
  environment: string;
  database: "ok" | "unavailable";
};

export type Me = { name: string | null; authenticated: boolean };

async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(path, { headers: { Accept: "application/json" } });
  // /api/health answers 503 with a body when the database is down; still parse it.
  if (!resp.ok && resp.status !== 503) {
    throw new Error(`${path} failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export const fetchHealth = () => getJson<Health>("/api/health");
export const fetchMe = () => getJson<Me>("/api/me");

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await fetch(path, {
    method,
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (resp.status === 204) return undefined as T;
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? "Some fields need fixing: " +
            detail.map((d: { loc?: string[] }) => d.loc?.at(-1) ?? "field").join(", ")
          : `Request failed (${resp.status}).`;
    throw new ApiError(message, resp.status);
  }
  return data as T;
}

// ---------- reference data (F1) ----------
export type AccountKind = "checking" | "savings" | "credit_card";
export type Owner = "Hernan" | "Lauren" | "Joint";
export type Country = "US" | "EC";
export type CategoryKind = "income" | "expense" | "savings" | "transfer";
export type MatchType = "contains" | "starts_with" | "regex";

export type Account = {
  account_id: number;
  name: string;
  institution: string;
  kind: AccountKind;
  owner: Owner;
  country: Country;
  last4: string | null;
  is_active: boolean;
};
export type AccountInput = Omit<Account, "account_id">;

export type Category = {
  category_id: number;
  parent_id: number | null;
  name: string;
  kind: CategoryKind;
  color: string | null;
  is_fixed: boolean;
  is_active: boolean;
  sort_order: number;
};
export type CategoryGroup = Category & { children: Category[] };

export type Rule = {
  rule_id: number;
  pattern: string;
  match_type: MatchType;
  category_id: number;
  category_path: string;
  priority: number;
  is_active: boolean;
  amount_min: Money | null; // on the absolute amount; null = no limit
  amount_max: Money | null;
};
export type RuleInput = Pick<Rule, "pattern" | "match_type" | "category_id" | "priority"> &
  Partial<Pick<Rule, "amount_min" | "amount_max">>;

export const fetchAccounts = () => send<Account[]>("GET", "/api/accounts");
export const createAccount = (a: AccountInput) => send<Account>("POST", "/api/accounts", a);
export const updateAccount = (id: number, a: Partial<AccountInput>) =>
  send<Account>("PATCH", `/api/accounts/${id}`, a);

export const fetchCategories = () => send<CategoryGroup[]>("GET", "/api/categories");
export const createCategory = (c: {
  name: string;
  parent_id?: number | null;
  kind?: CategoryKind;
  color?: string | null;
}) => send<Category>("POST", "/api/categories", c);
export const updateCategory = (
  id: number,
  c: Partial<Pick<Category, "name" | "color" | "is_fixed" | "is_active">>,
) => send<Category>("PATCH", `/api/categories/${id}`, c);

export const fetchRules = () => send<Rule[]>("GET", "/api/merchant-rules");
export const createRule = (r: RuleInput) => send<Rule>("POST", "/api/merchant-rules", r);
export const updateRule = (id: number, r: Partial<RuleInput & { is_active: boolean }>) =>
  send<Rule>("PATCH", `/api/merchant-rules/${id}`, r);
export const deleteRule = (id: number) => send<void>("DELETE", `/api/merchant-rules/${id}`);
export const testRule = (a: { description: string; amount?: string }) =>
  send<{ description: string; rule: Rule | null }>(
    "GET",
    `/api/merchant-rules/test?description=${encodeURIComponent(a.description)}` +
      (a.amount ? `&amount=${encodeURIComponent(a.amount)}` : ""),
  );

// ---------- history and cash flow (F2) ----------
// Money arrives as decimal strings; convert only for display and charts.
export type Money = string;

export type MonthlyCashflow = {
  cash_month: string;
  income: Money;
  expenses: Money;
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

async function upload<T>(path: string, file: File): Promise<T> {
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

export const fetchMonthly = () => send<MonthlyCashflow[]>("GET", "/api/cashflow/monthly");
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

// ---------- import batches and transactions (F4) ----------
export type Check = { name: string; expected: Money; actual: Money; ok: boolean };
export type StgLine = {
  stg_id: number;
  txn_date: string;
  post_date: string | null;
  description: string;
  merchant: string | null;
  amount: Money;
  type: string;
  category_id: number | null;
  category_path: string | null;
  person: string | null;
  country: string | null;
  cardholder: string | null;
  account_name?: string | null;
  pay_reference?: string | null;
  is_duplicate: boolean;
};
export type Batch = {
  batch_id: number;
  status: "preview" | "approved" | "rejected";
  tieout_ok: boolean;
  statement: Statement;
  period_start: string;
  period_end: string;
  opening_balance: Money | null;
  closing_balance: Money | null;
  checks: Check[];
  lines: StgLine[];
  by_category: { category_path: string; type: string; lines: number; amount: Money }[];
  rejects: { page: number; line_no: number; text: string; reason: string }[];
  new_lines: number;
  duplicate_lines: number;
  uncategorized: number;
  created_by: string;
  decided_by: string | null;
  decided_at: string | null;
};
export type Txn = {
  transaction_id: number;
  txn_date: string;
  post_date: string | null;
  cash_month: string;
  account_id: number | null;
  account_name: string | null;
  description: string;
  merchant: string | null;
  amount: Money;
  type: string;
  category_id: number | null;
  category_path: string | null;
  person: string | null;
  country: string | null;
  source: string;
  statement_file_id: number | null;
  notes: string | null;
  category_source: "rule" | "section" | "manual" | "suggestion" | "excel" | "split" | null;
  parent_transaction_id: number | null;
  parts: number; // > 0: split into this many parts, which count instead of this line
};

export const readStatement = (id: number) => send<Batch>("POST", `/api/statements/${id}/read`);
export const fetchBatch = (id: number) => send<Batch>("GET", `/api/batches/${id}`);
export const approveBatch = (id: number) =>
  send<{ batch_id: number; loaded: number; skipped_duplicates: number }>(
    "POST",
    `/api/batches/${id}/approve`,
  );
export const rejectBatch = (id: number) => send<Batch>("POST", `/api/batches/${id}/reject`);
export const fetchTransactions = (month: string) => send<Txn[]>("GET", `/api/transactions?month=${month}`);

// ---------- classification (F9) ----------
export type Suggestion = {
  category_id: number;
  category_path: string;
  confidence: string; // 0 to 1
  reason: string;
  model: string;
};
export type ReviewLine = {
  transaction_id: number;
  txn_date: string;
  amount: Money;
  description: string;
  account_name: string | null;
  person: string | null;
};
export type ReviewGroup = {
  merchant_key: string;
  lines: ReviewLine[];
  total: Money;
  suggestion: Suggestion | null;
};
export type Review = {
  month: string | null;
  groups: ReviewGroup[];
  uncategorized_lines: number;
  suggestions_available: boolean;
};
export type ResolveInput = {
  merchant_key: string;
  category_id: number;
  transaction_ids?: number[] | null;
  save_rule: boolean;
  pattern?: string | null;
  match_type?: MatchType;
  amount_min?: Money | null;
  amount_max?: Money | null;
  from_suggestion?: boolean;
};
export type Resolved = { categorized: number; rule_id: number | null; also_by_rule: number };
export type Change = {
  change_id: number;
  column_name: string;
  old_value: string | null;
  new_value: string | null;
  reason: string;
  changed_by: string;
  changed_at: string;
};
export type PartInput = { amount: Money; category_id: number; notes?: string | null };

const monthQuery = (month?: string | null) => (month ? `?month=${month}` : "");
export const fetchReview = (month?: string | null) => send<Review>("GET", `/api/review${monthQuery(month)}`);
export const resolveMerchant = (body: ResolveInput) => send<Resolved>("POST", "/api/review/resolve", body);
export const suggestCategories = (month?: string | null) =>
  send<{ asked: number; suggested: number; model: string }>(
    "POST",
    `/api/review/suggest${monthQuery(month)}`,
  );
export const updateTransaction = (
  id: number,
  body: { category_id?: number; notes?: string | null; person?: Owner | null },
) => send<Txn>("PATCH", `/api/transactions/${id}`, body);
export const splitTransaction = (id: number, parts: PartInput[]) =>
  send<Txn[]>("PUT", `/api/transactions/${id}/split`, { parts });
export const removeSplit = (id: number) => send<void>("DELETE", `/api/transactions/${id}/split`);
export const fetchHistory = (id: number) => send<Change[]>("GET", `/api/transactions/${id}/history`);
