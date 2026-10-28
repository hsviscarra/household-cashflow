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
  category_source: "rule" | "section" | "manual" | "suggestion" | "excel" | "split" | "match" | null;
  parent_transaction_id: number | null;
  parts: number; // > 0: split into this many parts, which count instead of this line
  transfer_group_id?: number | null;
  transfer_with?: TransferLeg | null; // the other side of a matched transfer (F10)
  recurring_entry_id?: number | null; // the recurring entry this line pays (F11)
};
export type TransferLeg = {
  transaction_id: number;
  txn_date: string;
  amount: Money;
  description: string;
  account_id: number | null;
  account_name: string | null;
  account_kind: string | null;
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

// ---------- transfers (F10) ----------
export const fetchUnmatchedTransfers = (month?: string | null) =>
  send<Txn[]>("GET", `/api/transfers/unmatched${month ? `?month=${month}` : ""}`);
export const matchTransfers = () => send<{ pairs: number }>("POST", "/api/transfers/match");
export const unlinkTransfer = (group: number) => send<void>("DELETE", `/api/transfers/${group}`);

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
  kind: "statement" | "import" | "uncategorized" | "transfer" | "recurring" | "balance";
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
};
export const fetchStatus = () => send<DataStatus>("GET", "/api/status");

// ---------------- F13: spending analytics ----------------
export type SpendCompare = { amount: string; prev: string; last_year: string; transactions: number };
export type SpendCategory = SpendCompare & { category_id: number; name: string };
export type SpendGroup = SpendCompare & {
  group_id: number;
  name: string;
  color: string | null;
  categories: SpendCategory[];
};
export type SpendSlice = { key: string; amount: string; transactions: number };
export type Spending = {
  month: string;
  months: string[];
  source: "excel" | "statements" | "none";
  total: SpendCompare;
  groups: SpendGroup[];
  by_person: SpendSlice[];
  by_country: SpendSlice[];
  fixed: SpendSlice[];
  merchants: { merchant: string; group_name: string; amount: string; transactions: number }[];
  trend: { month: string; amount: string }[];
};
export type SpendLine = {
  transaction_id: number;
  txn_date: string;
  merchant: string;
  description: string;
  amount: string;
  category_name: string;
  group_name: string;
  person: string;
  account_name: string | null;
  source: string;
};
export type SpendFilter = {
  group_id?: number;
  category_id?: number;
  merchant?: string;
  person?: string;
  country?: string;
  fixed?: boolean;
};
export const fetchSpending = (month?: string | null) =>
  send<Spending>("GET", `/api/spending${month ? `?month=${month}` : ""}`);
export const fetchSpendLines = (month: string, f: SpendFilter) => {
  const q = new URLSearchParams({ month });
  Object.entries(f).forEach(([k, v]) => v !== undefined && q.set(k, String(v)));
  return send<SpendLine[]>("GET", `/api/spending/lines?${q.toString()}`);
};

// ---------------- F14: subscriptions and cost of debt ----------------
export type SubscriptionCharge = {
  transaction_id: number;
  txn_date: string;
  amount: string;
  description: string;
  account_name: string | null;
};
export type Subscription = {
  merchant: string;
  cadence: "weekly" | "monthly" | "quarterly" | "yearly" | "possible";
  typical: string;
  monthly_cost: string;
  yearly_cost: string;
  category_path: string | null;
  accounts: string[];
  charges: SubscriptionCharge[];
  last: string;
  next_expected: string | null;
  active: boolean;
};
export type Subscriptions = {
  monthly_cost: string;
  weekly_monthly_cost: string;
  subscriptions: Subscription[];
};
export type DebtAccount = {
  account_id: number | null;
  name: string;
  kind: string | null;
  interest: string;
  fees: string;
  total: string;
  last_12: string;
  by_category: Record<string, string>;
  by_month: Record<string, string>;
  balance: string | null;
  balance_date: string | null;
};
export type Debt = {
  year: number;
  years: number[];
  through: string;
  months: string[];
  interest: string;
  fees: string;
  accounts: DebtAccount[];
};
export const fetchSubscriptions = () => send<Subscriptions>("GET", "/api/subscriptions");
export const fetchDebt = (year?: number | null) =>
  send<Debt>("GET", `/api/debt${year ? `?year=${year}` : ""}`);

// ---------------- F14: balance sheet ----------------
export type HoldingClass =
  "property" | "vehicle" | "investment" | "cash" | "purchase" | "loan" | "personal_loan" | "card" | "other";
export type SheetValue = {
  snapshot_id: number | null;
  as_of: string;
  amount: string;
  source: string;
  notes: string | null;
};
export type LoanSchedule = {
  installments: number;
  paid: number;
  left: number;
  next_period: string | null;
  next_total: string | null;
  payoff: string | null;
  balance: string | null;
  interest_this_year: string;
  interest_left: string;
  other_left: string;
};
export type LoanImport = {
  installments: number;
  paid: number;
  due: number;
  balance: string | null;
  as_of: string | null;
};
export type LoanPayment = {
  number: number;
  period: string;
  total: string;
  status: "paid" | "due";
  line_id: number | null;
  line_date: string | null;
  line_amount: string | null;
  line_description: string | null;
  account_name: string | null;
};
export type SheetItem = {
  key: string;
  name: string;
  side: "asset" | "liability";
  holding_class: HoldingClass;
  value: string | null;
  as_of: string | null;
  source: string | null;
  holding_id: number | null;
  account_id: number | null;
  is_active: boolean;
  notes: string | null;
  history: SheetValue[];
  purchase: {
    target: string;
    paid: string;
    remaining: string;
    installment: string | null;
    installments_left: number | null;
    full_price: string | null;
    at_delivery: string | null;
    lines: string;
  } | null;
  loan: {
    monthly_payment: string | null;
    paid_this_year: string;
    payments_this_year: number;
    schedule?: LoanSchedule | null;
  } | null;
  category_id: number | null;
  recurring_template_id: number | null;
};
export type BalanceSheet = {
  as_of: string;
  assets: string;
  liabilities: string;
  net_worth: string;
  commitments: string;
  items: SheetItem[];
  series: { month: string; assets: string; liabilities: string; net: string }[];
};
export type HoldingInput = {
  name: string;
  holding_class: HoldingClass;
  side?: "asset" | "liability" | null;
  value?: string | null;
  as_of?: string | null;
  target_amount?: string | null;
  installment?: string | null;
  full_price?: string | null;
  category_id?: number | null;
  recurring_template_id?: number | null;
  notes?: string | null;
};
export const fetchBalanceSheet = () => send<BalanceSheet>("GET", "/api/networth");
export const createHolding = (h: HoldingInput) => send<{ holding_id: number }>("POST", "/api/holdings", h);
export const updateHolding = (id: number, h: Partial<HoldingInput> & { is_active?: boolean }) =>
  send<{ holding_id: number }>("PATCH", `/api/holdings/${id}`, h);
export const deleteHolding = (id: number) => send<void>("DELETE", `/api/holdings/${id}`);
export const setHoldingValue = (id: number, v: { as_of: string; amount: string; notes?: string | null }) =>
  send<SheetValue>("POST", `/api/holdings/${id}/values`, v);
export const uploadLoanTable = (id: number, file: File) =>
  upload<LoanImport>(`/api/holdings/${id}/schedule`, file);
export const fetchLoanPayments = (id: number) => send<LoanPayment[]>("GET", `/api/holdings/${id}/payments`);
export const deleteHoldingValue = (snapshotId: number) =>
  send<void>("DELETE", `/api/holdings/values/${snapshotId}`);

// ---------------- F15: projections ----------------
export type ProjectionEvent = {
  day: string;
  name: string;
  amount: string;
  kind: "income" | "fixed" | "purchase" | "variable";
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
};
export const fetchProjection = () => send<Projection>("GET", "/api/projections");
