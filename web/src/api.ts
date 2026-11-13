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

// ---------- per-person settings (ADR-026) ----------
export type Settings = { user: string; settings: Record<string, unknown> };
export const fetchSettings = () => send<Settings>("GET", "/api/me/settings");
export const putSetting = (key: string, value: unknown) =>
  send<Settings>("PUT", `/api/me/settings/${encodeURIComponent(key)}`, { value });

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
export type CategoryKind = "income" | "expense" | "savings" | "transfer" | "debt";
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
  closed_on?: string | null; // closed or suspended: no statements expected after this day
  opened_on?: string | null; // opened: no statements expected before this day
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
  description?: string | null; // what goes here (F23)
  lines?: number; // loaded lines in it
  rules?: number; // merchant rules pointing at it
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
  set_person: Owner | null; // the rule also sets whose line it is (ADR-042)
  merchant_name: string | null; // and the merchant name shown
  applied?: number; // lines this save categorized (loaded or waiting for approval)
};
export type RuleInput = Pick<Rule, "pattern" | "match_type" | "category_id" | "priority"> &
  Partial<Pick<Rule, "amount_min" | "amount_max" | "set_person" | "merchant_name">>;
export type RuleSuggestion = {
  pattern: string;
  category_id: number;
  category_path: string;
  times: number;
  example: string;
  person: Owner | null;
};

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
  description?: string | null;
}) => send<Category>("POST", "/api/categories", c);
export const updateCategory = (
  id: number,
  c: Partial<Pick<Category, "name" | "color" | "is_fixed" | "is_active" | "description" | "parent_id">>,
) => send<Category>("PATCH", `/api/categories/${id}`, c);

export const fetchRules = () => send<Rule[]>("GET", "/api/merchant-rules");
export type SyncAccount = {
  sync_id: string;
  org: string;
  name: string;
  balance: string;
  balance_date: string;
  account_id: number | null;
  movements: number;
};
export type BankSync = {
  configured: boolean;
  due: boolean;
  last_run: {
    at: string;
    by: string;
    added: number;
    already: number;
    covered: number;
    unlinked: number;
    accounts: SyncAccount[];
    errors: string[];
  } | null;
  pending_lines: number;
  accounts: { account_id: number; name: string; institution: string; sync_id: string | null }[];
  ran?: boolean;
  added?: number;
};
// ---------------- To do (ADR-047) ----------------
export type TodoTask = {
  key: string;
  kind: string; // categorize, who, transfer, statement, import, recurring, balance, note, stale, duplicate, rule, bill, invoices
  title: string;
  detail: string;
  amount: Money | null;
  on: string | null;
  link: string;
  data: Record<string, unknown>;
};
export type TodoSection = { key: string; title: string; hint: string; tasks: TodoTask[]; count: number };
export type Todo = { today: string; total: number; sections: TodoSection[] };
// ---------------- Where's the money (ADR-051) ----------------
export type Reconcile = {
  start: string;
  end: string;
  money_in: Money;
  money_out: Money;
  kept: Money;
  balances_change: Money;
  gap: Money;
  accounts: {
    account_id: number;
    name: string;
    kind: "cash" | "card";
    start: Money | null;
    start_on: string | null;
    end: Money | null;
    end_on: string | null;
    change: Money | null;
  }[];
  causes: { key: string; title: string; detail: string; amount: Money; link: string }[];
  workbook_months: number;
};
export const fetchReconcile = (from: string, to: string) =>
  send<Reconcile>("GET", `/api/reconcile?from=${from}&to=${to}`);
export const markInstallmentPaid = (holding_id: number, number: number) =>
  send<{ number: number; period: string; balance_after: Money }>(
    "POST",
    `/api/holdings/${holding_id}/installments/${number}/paid`,
  );
export const fetchTodo = () => send<Todo>("GET", "/api/todo");
/** Let a suggestion or an out-of-date value go: it isn't asked again (ADR-058). */
export const dismissTodo = (key: string) => send<void>("POST", "/api/todo/dismiss", { key });
export const fetchBankSync = () => send<BankSync>("GET", "/api/bank-sync");
export const runBankSync = (auto = false) =>
  send<BankSync>("POST", `/api/bank-sync/run${auto ? "?auto=true" : ""}`);
export const linkBankSync = (b: { sync_id: string; account_id: number | null }) =>
  send<BankSync>("PUT", "/api/bank-sync/link", b);
export const fetchRuleSuggestions = () => send<RuleSuggestion[]>("GET", "/api/merchant-rules/suggestions");
export const createRule = (r: RuleInput) => send<Rule>("POST", "/api/merchant-rules", r);
export const updateRule = (id: number, r: Partial<RuleInput & { is_active: boolean }>) =>
  send<Rule>("PATCH", `/api/merchant-rules/${id}`, r);
export const deleteRule = (id: number) => send<void>("DELETE", `/api/merchant-rules/${id}`);
/** What uses a category, or what moved when it was deleted (ADR-034). */
export type CategoryUses = {
  lines: number;
  rules: number;
  bills: number;
  budgets: number;
  other: number;
  total: number;
};
export const fetchCategoryUses = (id: number) => send<CategoryUses>("GET", `/api/categories/${id}/uses`);
export const deleteCategory = (id: number, moveTo?: number | null) =>
  send<CategoryUses>("DELETE", `/api/categories/${id}${moveTo ? `?move_to=${moveTo}` : ""}`);
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
  hint_source?: "note" | "person" | null;
  hint_person?: string | null;
  hint_text?: string | null;
  hint_share?: Money | null;
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
  /** On the answer to an edit: the rule saved because this merchant got the same category twice (ADR-079). */
  learned?: { rule_id: number; pattern: string; lines: number } | null;
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
  category_source:
    | "rule"
    | "section"
    | "manual"
    | "suggestion"
    | "excel"
    | "split"
    | "match"
    | "note"
    | "person"
    | "invoice"
    | null;
  parent_transaction_id: number | null;
  parts: number; // > 0: split into this many parts, which count instead of this line
  transfer_group_id?: number | null;
  transfer_with?: TransferLeg | null; // the other side of a matched transfer (F10)
  recurring_entry_id?: number | null; // the recurring entry this line pays (F11)
  counterparty_id?: number | null; // whose money it is or who it was for (ADR-023)
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
export type ApproveReady = {
  approved: number;
  loaded: number;
  waiting: { batch_id: number; file_name: string; reason: string }[];
};
export const approveReady = () => send<ApproveReady>("POST", "/api/batches/approve-ready");
export const approveBatch = (id: number) =>
  send<{ batch_id: number; loaded: number; skipped_duplicates: number }>(
    "POST",
    `/api/batches/${id}/approve`,
  );
export const applyRules = (id: number) =>
  send<{ categorized: number; batch: Batch }>("POST", `/api/batches/${id}/apply-rules`);
export const rejectBatch = (id: number) => send<Batch>("POST", `/api/batches/${id}/reject`);
export const fetchTransactions = (
  month: string,
  person?: string,
  f: { months?: number; counterparty_id?: number } = {},
) =>
  send<Txn[]>(
    "GET",
    `/api/transactions?month=${month}${person ? `&person=${person}` : ""}${f.months && f.months > 1 ? `&months=${f.months}&limit=2000` : ""}${f.counterparty_id ? `&counterparty_id=${f.counterparty_id}` : ""}`,
  );

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
  post_date?: string | null;
  statement_file_id?: number | null; // open the statement at this page (ADR-034)
  page?: number | null;
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
export type Resolved = {
  categorized: number;
  rule_id: number | null;
  also_by_rule: number;
  waiting_by_rule?: number; // lines in statements not approved yet
};
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

// F23: one click for Claude's likely suggestions, and categorizing a statement before approval.
export type Accepted = { merchants: number; lines: number; also_by_rule: number };
export const acceptSuggestions = (month?: string | null) =>
  send<Accepted>("POST", `/api/review/accept-suggestions${monthQuery(month)}`);
export const fetchBatchReview = (id: number) => send<Review>("GET", `/api/batches/${id}/review`);
export const resolveBatchMerchant = (id: number, body: ResolveInput) =>
  send<Resolved>("POST", `/api/batches/${id}/resolve`, body);
export const suggestBatch = (id: number) =>
  send<{ asked: number; suggested: number; model: string }>("POST", `/api/batches/${id}/suggest`);
export const acceptBatchSuggestions = (id: number) =>
  send<Accepted>("POST", `/api/batches/${id}/accept-suggestions`);
export const updateTransaction = (
  id: number,
  body: { category_id?: number; notes?: string | null; person?: Owner | null; counts_in?: string | null },
) => send<Txn>("PATCH", `/api/transactions/${id}`, body);
export const splitTransaction = (id: number, parts: PartInput[]) =>
  send<Txn[]>("PUT", `/api/transactions/${id}/split`, { parts });
export const removeSplit = (id: number) => send<void>("DELETE", `/api/transactions/${id}/split`);
export const fetchHistory = (id: number) => send<Change[]>("GET", `/api/transactions/${id}/history`);

// ---------- where a line came from (ADR-034) ----------
export type LineSource = {
  transaction_id: number;
  txn_date: string;
  post_date: string | null;
  amount: Money;
  description: string;
  account_name: string | null;
  account_last4: string | null;
  person: string | null;
  pay_reference: string | null;
  notes: string | null;
  statement_file_id: number | null;
  file_name: string | null;
  bank: string | null;
  period_start: string | null;
  period_end: string | null;
  page: number | null;
  line_no: number | null;
  section: string | null;
  cardholder: string | null;
  text: string | null;
  around: { line_no: number; text: string; is_line: boolean }[];
  note_from: string | null;
  note_person: string | null;
  note: string | null;
  similar: {
    txn_date: string;
    amount: Money;
    description: string;
    category_id: number | null;
    category_path: string | null;
  }[];
  unreadable: boolean;
};
export const fetchLineSource = (id: number) => send<LineSource>("GET", `/api/transactions/${id}/source`);
export const fetchStagedSource = (batchId: number, stgId: number) =>
  send<LineSource>("GET", `/api/batches/${batchId}/lines/${stgId}/source`);
/** The statement PDF, opened at a page when the browser's viewer supports it. */
// ---------- what's known about a line (ADR-074) ----------
export type ContextLine = {
  transaction_id: number;
  txn_date: string;
  amount: string;
  description: string;
  account_name: string | null;
  category_path: string | null;
  type: string;
};
export type LineContext = {
  transaction_id: number;
  category_source: string | null;
  rule: {
    rule_id: number;
    pattern: string;
    match_type: string;
    category_path: string | null;
    amount_min: string | null;
    amount_max: string | null;
  } | null;
  same_amount: ContextLine[];
  transfer_side: ContextLine[];
  transfer_candidates: ContextLine[];
  invoices: {
    invoice_id: number;
    issuer_name: string;
    issue_date: string;
    total: string;
    products: string[];
    linked: boolean;
  }[];
  purpose: { account_name: string; for_whom: string; usual: string[]; unusual: boolean } | null;
};
export const fetchLineContext = (id: number) => send<LineContext>("GET", `/api/transactions/${id}/context`);
export const linkInvoice = (id: number, invoice_id: number) =>
  send<{ invoice_id: number }>("PUT", `/api/transactions/${id}/invoice`, { invoice_id });
export const statementPageUrl = (id: number, page?: number | null) =>
  `/api/statements/${id}/file${page ? `#page=${page}` : ""}`;

// ---------- transfers (F10) ----------
export type TransferCandidate = {
  transaction_id: number;
  txn_date: string;
  amount: string;
  description: string;
  account_name: string | null;
  days: number;
  /** How much less arrived than left: pairing books it as a bank fee (ADR-080). */
  difference?: string;
};
export type UnsettledLine = {
  transaction_id: number;
  txn_date: string;
  amount: string;
  description: string;
  account_name: string | null;
  category_id: number | null;
  statement_file_id: number | null;
  candidates: TransferCandidate[];
};
export type TransferBunch = { key: string; description: string; amount: string; lines: UnsettledLine[] };
export const fetchTransferWorkbench = () =>
  send<{ places: string[]; bunches: TransferBunch[] }>("GET", "/api/transfers/workbench");
export const pairTransfer = (a: number, b: number) =>
  send<{ group: number }>("POST", "/api/transfers/pair", { a, b });
export const settleOutside = (ids: number[], place: string) =>
  send<{ settled: number }>("POST", "/api/transfers/outside", { ids, place });
export const fetchUnmatchedTransfers = (month?: string | null) =>
  send<Txn[]>("GET", `/api/transfers/unmatched${month ? `?month=${month}` : ""}`);
export const matchTransfers = () => send<{ pairs: number }>("POST", "/api/transfers/match");
export const unlinkTransfer = (group: number) => send<void>("DELETE", `/api/transfers/${group}`);
/** The other side is in an account the app doesn't follow: stop asking for it (ADR-058). */
export const oneSidedTransfer = (transaction_id: number) =>
  send<void>("POST", `/api/transfers/${transaction_id}/one-sided`);

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
  state: "loaded" | "waiting" | "problems" | "not_read";
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
export const fetchSpending = (month?: string | null, person?: string) => {
  const q = new URLSearchParams();
  if (month) q.set("month", month);
  if (person) q.set("person", person);
  const qs = q.toString();
  return send<Spending>("GET", `/api/spending${qs ? `?${qs}` : ""}`);
};
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
  price_up?: string | null; // how much the last charge is over the earlier ones (ADR-097)
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
// ---------- the four measures (ADR-073) ----------
export type MeasurePeriod = {
  month: string;
  start: string;
  end: string;
  money_in: string;
  spent: string;
  set_aside: string;
  free_cash: string;
  left_over: string;
};
export type MonthMeasures = {
  month: string;
  through: string;
  running: boolean;
  this: MeasurePeriod;
  before: MeasurePeriod;
  months: MeasurePeriod[];
};
export const fetchMeasures = (month: string, person?: string | null, months?: number) =>
  send<MonthMeasures>(
    "GET",
    `/api/cashflow/measures${query({ month, person: person ?? undefined, months })}`,
  );
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
type ReportFlow = {
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

// ---------- F22: Interactive Brokers ----------
export type Position = {
  symbol: string;
  description: string | null;
  asset_class: string;
  currency: string;
  quantity: string;
  price: string;
  value: string;
  cost_basis: string | null;
  unrealized: string | null;
};
export type Portfolio = {
  holding_id: number | null;
  as_of: string | null;
  total: string | null;
  cash: string | null;
  previous_total: string | null;
  previous_as_of: string | null;
  stale: boolean;
  positions: Position[];
};
export type PortfolioRead = {
  holding_id: number;
  as_of: string;
  total: string;
  cash: string;
  positions: number;
};
export const fetchPortfolio = () => send<Portfolio>("GET", "/api/investments/ibkr");
export const uploadFlex = (file: File) => upload<PortfolioRead>("/api/investments/ibkr/upload", file);

// ---------- F21: electronic invoices ----------
export type InvoiceLine = {
  line_no: number;
  description: string;
  product_key: string;
  quantity: string;
  unit_price: string;
  total: string;
  product_group: string | null;
  group_source: "rule" | "keyword" | "claude" | "confirmed" | null;
  category_id?: number | null; // the app category (ADR-050)
  category_path?: string | null;
};
export type Invoice = {
  invoice_id: number;
  issuer_name: string;
  number: string;
  issue_date: string;
  subtotal: string;
  tax: string;
  total: string;
  received_by: string;
  paid_with: { transaction_id: number; txn_date: string; account: string | null; description: string } | null;
  lines: InvoiceLine[];
};
export type Purchases = {
  month: string;
  total: string;
  matched_total: string;
  groups: { group: string; amount: string; lines: number }[];
  to_group: {
    product_key: string;
    description: string;
    lines: number;
    amount: string;
    suggested_group: string | null;
  }[];
  invoices: Invoice[];
  product_groups: string[];
  suggestions_available: boolean;
};
export type InvoiceUpload = {
  file_name: string;
  outcome: "stored" | "duplicate" | "skipped" | "rejected";
  message: string;
  invoice_id: number | null;
};
export const fetchPurchases = (month: string) =>
  send<Purchases>("GET", `/api/invoices?month=${encodeURIComponent(month)}`);
export const setProductGroup = (product_key: string, product_group: string) =>
  send<{ product_key: string; product_group: string; lines_updated: number }>(
    "PUT",
    "/api/invoices/products",
    {
      product_key,
      product_group,
    },
  );
export const setProductCategory = (product_key: string, category_id: number | null) =>
  send<{ product_key: string; category_id: number | null; lines_updated: number }>(
    "PUT",
    "/api/invoices/products",
    { product_key, category_id },
  );
export const suggestProductGroups = (month: string) =>
  send<{ products: number }>("POST", `/api/invoices/suggest?month=${encodeURIComponent(month)}`);

export async function uploadInvoices(files: File[]): Promise<InvoiceUpload[]> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const resp = await fetch("/api/invoices", {
    method: "POST",
    body: form,
    headers: { Accept: "application/json" },
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail;
    throw new ApiError(typeof detail === "string" ? detail : `Upload failed (${resp.status}).`, resp.status);
  }
  return data as InvoiceUpload[];
}

// ---------- people and transfer notes (ADR-023) ----------
export type Person = {
  counterparty_id: number;
  name: string;
  patterns: string | null;
  category_id: number | null;
  category_path: string | null;
  holding_id: number | null;
  holding_name: string | null;
  is_active: boolean;
  notes: string | null;
  lines: number;
  received: string;
  paid: string;
};
export type PersonInput = {
  name: string;
  patterns?: string | null;
  category_id?: number | null;
  holding_id?: number | null;
  notes?: string | null;
  new_balance?: boolean;
  opening_balance?: string | null;
  opening_as_of?: string | null;
};
export type PersonLine = {
  transaction_id: number;
  txn_date: string;
  amount: string;
  description: string;
  account_name: string | null;
  category_path: string | null;
  notes: string | null;
};
export type TransferNote = {
  note_id: number;
  txn_date: string;
  amount: string;
  account_id: number | null;
  account_name: string | null;
  counterparty_id: number | null;
  person: string | null;
  category_id: number | null;
  category_path: string | null;
  other_party: string | null;
  description: string | null;
  share: string | null;
  source: "manual" | "email";
  transaction_id: number | null;
  line_date: string | null;
  line_description: string | null;
  created_by: string;
};
export type NoteInput = {
  txn_date: string;
  direction: "sent" | "received";
  amount: string;
  account_id?: number | null;
  counterparty_id?: number | null;
  category_id?: number | null;
  other_party?: string | null;
  description?: string | null;
  share?: string | null;
};

export const fetchPeople = () => send<Person[]>("GET", "/api/people");
export const createPerson = (p: PersonInput) => send<Person>("POST", "/api/people", p);
export const updatePerson = (id: number, p: Partial<PersonInput> & { is_active?: boolean }) =>
  send<Person>("PATCH", `/api/people/${id}`, p);
export const deletePerson = (id: number) => send<void>("DELETE", `/api/people/${id}`);
export const fetchPersonLines = (id: number) => send<PersonLine[]>("GET", `/api/people/${id}/lines`);
export const fetchNotes = (state: "open" | "matched" | "all" = "all") =>
  send<TransferNote[]>("GET", `/api/transfer-notes?state=${state}`);
export const createNote = (n: NoteInput) => send<TransferNote>("POST", "/api/transfer-notes", n);
export const deleteNote = (id: number) => send<void>("DELETE", `/api/transfer-notes/${id}`);
export const matchNotes = () =>
  send<{ matched: number; tagged: number }>("POST", "/api/transfer-notes/match");

// ---------- Cash flow: one month by category, and the lines behind it (ADR-027) ----------
export type Flow = {
  type: string;
  group_id: number;
  group_name: string;
  group_color: string | null;
  category_id: number;
  category_name: string;
  amount: string;
  prev: string;
  transactions: number;
};
export type Flows = {
  month: string;
  prev_month: string;
  months: string[];
  source: "excel" | "statements" | "none";
  flows: Flow[];
  trend: { month: string; money_in: string; money_out: string }[];
};
export type FlowLine = {
  transaction_id: number;
  txn_date: string;
  description: string;
  merchant: string | null;
  amount: string;
  type: string;
  category_name: string | null;
  account_name: string | null;
  person: string | null;
  source: string;
  notes: string | null;
  category_id?: number | null;
  statement_file_id?: number | null;
  counterparty?: string | null;
  merchant_key?: string;
  cash_month?: string | null;
  month_override?: string | null; // a person chose the month it counts in (ADR-089)
};
export type FlowFilter = {
  side?: "in" | "out";
  group_id?: number;
  category_id?: number;
  merchant?: string;
  person?: string;
  type?: string;
};
const query = (o: Record<string, string | number | undefined | null>) => {
  const q = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => v !== undefined && v !== null && q.set(k, String(v)));
  const s = q.toString();
  return s ? `?${s}` : "";
};
export const fetchFlows = (month?: string | null, person?: string) =>
  send<Flows>("GET", `/api/cashflow/flows${query({ month, person })}`);
export const fetchFlowLines = (month: string, f: FlowFilter) =>
  send<FlowLine[]>("GET", `/api/cashflow/lines${query({ month, ...f })}`);
export const searchLines = (q: string, month: string) =>
  send<FlowLine[]>("GET", `/api/cashflow/search${query({ q, month })}`);

// ---------- Spending, one level deeper (ADR-028) ----------
export type MerchantRow = {
  merchant: string;
  group_id: number;
  group_name: string;
  amount: string;
  visits: number;
  avg_ticket: string;
  invoices: number;
};
export type ProductRow = {
  product_key: string;
  description: string;
  product_group: string | null;
  times: number;
  quantity: string;
  amount: string;
  unit_price: string;
  before: string | null;
  change: string | null;
  stores: string[];
  cheaper_store: string | null;
  cheaper_price: string | null;
  could_save: string;
};
export type Idea = {
  key: string;
  title: string;
  detail: string;
  amount: string;
  count: number;
  link: string | null;
};
export const fetchMerchants = (
  month: string,
  f: { person?: string; group_id?: number; category_id?: number },
) => send<MerchantRow[]>("GET", `/api/spending/merchants${query({ month, ...f })}`);
export const fetchProducts = (month: string, product_group?: string) =>
  send<ProductRow[]>("GET", `/api/spending/products${query({ month, product_group })}`);
// ---------- Groceries (ADR-059) ----------
export type Groceries = {
  month: string;
  spent: Money;
  usual: Money;
  invoiced: Money;
  weeks: Money;
  trend: { month: string; spent: Money; invoiced: Money }[];
  aisles: { name: string; amount: Money; lines: number; usual: Money }[];
  products: ProductRow[];
  stores: { name: string; invoices: number; amount: Money }[];
  missing: {
    transaction_id: number;
    txn_date: string;
    merchant: string;
    amount: Money;
    account_name: string | null;
  }[];
  ungrouped_products: number;
};
export const fetchGroceries = (month: string) =>
  send<Groceries>("GET", `/api/spending/groceries${query({ month })}`);
export type GroceryTrendMonth = {
  month: string;
  spent: string;
  invoiced: string;
  trips: number;
  basket: string;
  aisles: Record<string, string>;
};
export type GroceryCell = {
  month: string;
  aisle: string;
  type: string | null;
  brand: string | null;
  amount: string;
  lines: number;
};
export type GroceryMover = {
  product_key: string;
  description: string;
  aisle: string;
  first_month: string;
  first_price: string;
  last_month: string;
  last_price: string;
  change: string;
  amount: string;
};
export type GroceryRegular = {
  product_key: string;
  description: string;
  aisle: string;
  months: number;
  usual: string;
};
export type GroceryTrends = {
  month: string;
  months: GroceryTrendMonth[];
  aisles: string[];
  cells: GroceryCell[];
  weekdays: { day: number; trips: number; amount: string }[];
  risers: GroceryMover[];
  fallers: GroceryMover[];
  new: GroceryRegular[];
  skipped: GroceryRegular[];
};
export const fetchGroceryTrends = (month: string, months = 12) =>
  send<GroceryTrends>("GET", `/api/spending/groceries/trends${query({ month, months: String(months) })}`);
export type GroceryProduct = {
  product_key: string;
  description: string;
  product_group: string | null;
  product_type: string | null;
  brand: string | null;
  label_source: "claude" | "confirmed" | null;
  times: number;
  quantity: Money;
  amount: Money;
  unit_price: Money;
  stores: string[];
};
export type GroceryTotal = { name: string; amount: Money; products: number };
export type GroceryProducts = {
  start: string;
  months: number;
  total: Money;
  products: GroceryProduct[];
  by_group: GroceryTotal[];
  by_type: GroceryTotal[];
  by_brand: GroceryTotal[];
  unlabeled: number;
};
export const fetchGroceryProducts = (start: string, months: number) =>
  send<GroceryProducts>("GET", `/api/spending/groceries/products${query({ start, months: String(months) })}`);
export const labelGroceries = (start: string, months: number) =>
  send<{ labeled: number }>(
    "POST",
    `/api/spending/groceries/label${query({ start, months: String(months) })}`,
  );
export const setGroceryLabels = (body: {
  product_key: string;
  product_group?: string | null;
  product_type?: string | null;
  brand?: string | null;
}) => send<{ lines: number }>("PUT", "/api/spending/groceries/products", body);
// ---------- Monthly IVA (ADR-062) ----------
export type IvaUse = "business" | "personal" | "none";
export type IvaMonth = {
  person: string;
  month: string;
  sales: {
    number: string;
    issue_date: string;
    buyer_name: string;
    base_taxed: Money;
    base_zero: Money;
    tax: Money;
    total: Money;
    income_tax_withheld: Money;
    iva_withheld: Money;
  }[];
  purchases: {
    invoice_id: number;
    issuer_ruc: string;
    issuer_name: string;
    number: string;
    issue_date: string;
    base_taxed: Money;
    base_zero: Money;
    tax: Money;
    total: Money;
    iva_use: IvaUse | null;
    access_key: string;
  }[];
  withholdings: {
    issuer_name: string;
    number: string;
    issue_date: string;
    invoice_number: string | null;
    income_tax: Money;
    iva: Money;
  }[];
  form: Record<string, Money | number>;
  tax_notes: {
    kind: "credit" | "debit";
    direction: "issued" | "received";
    name: string;
    number: string;
    issue_date: string;
    modified_number: string | null;
    base_taxed: Money;
    base_zero: Money;
    tax: Money;
    total: Money;
    counts: boolean;
  }[];
  opening_month: string | null;
  unclassified: number;
  income_tax_withheld: Money;
  notes: string[];
};
export const fetchIva = (month: string) => send<IvaMonth>("GET", `/api/taxes/iva${query({ month })}`);
export const ivaExcelUrl = (month: string) => `/api/taxes/iva/excel${query({ month })}`;
export const setIvaIssuer = (issuer_ruc: string, iva_use: IvaUse) =>
  send<void>("PUT", "/api/taxes/iva/issuers", { issuer_ruc, iva_use });
export const setIvaOpening = (b: {
  person: string;
  month: string;
  purchase_credit: string;
  retention_credit: string;
}) => send<void>("PUT", "/api/taxes/iva/opening", b);
export const fetchIdeas = (month: string, person?: string) =>
  send<Idea[]>("GET", `/api/spending/ideas${query({ month, person })}`);

// ---------- the Inbox doing more of the work (ADR-029) ----------
export type AutoRule = {
  rule_id: number;
  pattern: string;
  category_id: number;
  category_path: string;
  lines: number;
  accepted_at: string;
  is_active: boolean;
};
export type AutoState = { threshold: string; on: boolean; rules: AutoRule[] };
export type Many = { merchants: number; lines: number; also_by_rule: number; skipped: number };
export const fetchAuto = () => send<AutoState>("GET", "/api/review/auto");
export const undoAuto = (ruleId: number) =>
  send<{ lines: number }>("POST", `/api/review/auto/${ruleId}/undo`);
export const resolveMany = (merchant_keys: string[], category_id: number | null) =>
  send<Many>("POST", "/api/review/resolve-many", { merchant_keys, category_id, save_rule: true });
export const fetchWho = (month?: string | null) => send<Txn[]>("GET", `/api/review/who${query({ month })}`);
export const setWho = (transaction_id: number, counterparty_id: number) =>
  send<Txn>("POST", "/api/review/who", { transaction_id, counterparty_id });

// ---------- Bills & subscriptions (ADR-031) ----------
export type BillStatus = "paid" | "due" | "late" | "waiting" | "skipped";
export type Bill = {
  template_id: number;
  entry_id: number | null; // this month's entry, when the month was generated
  name: string;
  type: TemplateType;
  group: string;
  group_color: string | null;
  category_path: string;
  account_name: string | null;
  every_months: number;
  due_day: number | null;
  due_day_set: boolean;
  expected: string;
  paid: string | null;
  lines: number;
  status: BillStatus;
  avg3: string | null;
  payments_left: number | null;
  price_from: string | null;
  price_changed: string | null;
  end_month: string | null;
};
export type Bills = { month: string; today: string; bills: Bill[] };
/** The bill doesn't apply from `month` (YYYY-MM-01) on (ADR-089). */
export const stopTemplate = (id: number, month: string) =>
  send<{ count: number }>("POST", `/api/recurring/templates/${id}/stop`, { month });
export const fetchBills = (month: string) => send<Bills>("GET", `/api/recurring/bills?month=${month}`);

// ---------- gastos personales (ADR-036) ----------
export type GpCategory = "vivienda" | "educacion" | "salud" | "alimentacion" | "vestimenta" | "turismo";
export type GastosPerson = {
  person: "Hernan" | "Lauren";
  cargas: number;
  catastrophic: boolean;
  cap: Money | null;
  total: Money;
  deductible: Money;
  rebate: Money;
  by_category: { category: GpCategory; label: string; invoices: number; amount: Money }[];
  to_classify: number;
  not_deductible: number;
};
export type GastosSummary = {
  year: number;
  canasta: Money | null;
  rate: Money;
  people: GastosPerson[];
  unassigned: number;
  unassigned_amount: Money;
  labels: Record<GpCategory, string>;
};
export type GastosInvoice = {
  invoice_id: number;
  issue_date: string;
  issuer_ruc: string;
  issuer_name: string;
  number: string;
  subtotal: Money;
  total: Money;
  person: "Hernan" | "Lauren" | null;
  person_source: "invoice" | "paid" | null;
  category: GpCategory | "none" | null;
  category_source: "chosen" | "issuer" | "claude" | "paid" | "products" | null;
  transaction_id: number | null;
  paid_as: string | null;
  category_id: number | null; // the app category: chosen for the invoice, else the paying line's
  category_path: string | null;
};
export type GastosChoice = {
  person?: "Hernan" | "Lauren" | null;
  category?: GpCategory | "none" | null;
  category_id?: number | null;
  remember_issuer?: boolean;
};
export const fetchGastos = (year: number) => send<GastosSummary>("GET", `/api/gastos/${year}`);
export const fetchGastosInvoices = (year: number, filter: "to_classify" | "nobody" | "all") =>
  send<GastosInvoice[]>(
    "GET",
    `/api/gastos/${year}/invoices${filter === "to_classify" ? "?status=to_classify" : filter === "nobody" ? "?person=none" : ""}`,
  );
export const chooseGastos = (invoiceId: number, body: GastosChoice) =>
  send<GastosInvoice>("PUT", `/api/invoices/${invoiceId}/gastos`, body);
export const setGastosProfile = (year: number, person: string, cargas: number, catastrophic: boolean) =>
  send<{ cap: Money | null }>("PUT", `/api/gastos/${year}/profile/${person}`, { cargas, catastrophic });
export const gastosCsvUrl = (year: number, person: string) => `/api/gastos/${year}/${person}.csv`;

// ---------- invoices from the SRI by access key (ADR-037) ----------
export type SriKeys = { new: string[]; stored: number; other: number };
export const findSriKeys = (text: string) => send<SriKeys>("POST", "/api/invoices/sri/keys", { text });
export const fetchSriInvoices = (keys: string[]) =>
  send<InvoiceUpload[]>("POST", "/api/invoices/sri/fetch", { keys });

// ---------- budget per group (ADR-039) ----------
export type GroupBudget = {
  group_id: number;
  name: string;
  color: string | null;
  budget: Money | null;
  rollover: boolean;
  carried: Money;
  spent: Money;
  available: Money;
  left: Money;
  expected: Money;
  status: "over" | "ahead" | "on_track" | "none";
  suggested: Money | null;
  since: string | null;
};
export type MonthBudget = {
  month: string;
  day_share: Money;
  groups: GroupBudget[];
  budgeted: Money;
  spent: Money;
  unbudgeted: Money;
  left: Money;
  has_plans: boolean;
};
export const fetchBudget = (month: string) => send<MonthBudget>("GET", `/api/budget/${month}`);
export const setBudget = (groupId: number, fromMonth: string, amount: string, rollover: boolean) =>
  send<void>("PUT", `/api/budget/groups/${groupId}`, { from_month: fromMonth, amount, rollover });
export const startBudgetFromAverage = (month: string) =>
  send<{ added: number }>("POST", `/api/budget/${month}/start-from-average`);

// ---------- saving goals (ADR-040) ----------
export type Goal = {
  goal_id: number;
  name: string;
  target_amount: Money;
  target_date: string | null;
  item_key: string | null;
  place_name: string | null;
  saved_amount: Money | null;
  monthly_amount: Money | null;
  is_active: boolean;
  notes: string | null;
  current: Money;
  as_of: string | null;
  share: Money;
  left: Money;
  months_left: number | null;
  needed_monthly: Money | null;
  projected: Money | null;
  status: "reached" | "on_pace" | "behind" | "late" | "open";
};
export type GoalPlace = { key: string; name: string; value: Money | null; as_of: string | null };
export type GoalInput = {
  name?: string;
  target_amount?: string;
  target_date?: string | null;
  item_key?: string | null;
  saved_amount?: string | null;
  monthly_amount?: string | null;
  is_active?: boolean;
  notes?: string | null;
};
export const fetchGoals = () => send<{ goals: Goal[]; places: GoalPlace[] }>("GET", "/api/goals");
export const createGoal = (body: GoalInput) => send<Goal>("POST", "/api/goals", body);
export const updateGoal = (id: number, body: GoalInput) => send<Goal>("PATCH", `/api/goals/${id}`, body);
export const deleteGoal = (id: number) => send<void>("DELETE", `/api/goals/${id}`);

// ---------- yearly bills as a monthly set-aside (ADR-041) ----------
export type SinkingFund = {
  template_id: number;
  name: string;
  every_months: number;
  amount: Money;
  monthly: Money;
  next_due: string;
  months_to_go: number;
  should_have: Money;
};
export const fetchYearlyBills = (month: string) =>
  send<SinkingFund[]>("GET", `/api/budget/${month}/yearly-bills`);

// ---------- email alerts (ADR-082) ----------
export type AlertSettings = { kinds: { key: string; label: string; on: boolean }[]; now: string[] };
export const fetchAlertSettings = () => send<AlertSettings>("GET", "/api/alerts");
export const saveAlertSettings = (off: string[]) => send<AlertSettings>("PUT", "/api/alerts", { off });

// ---------------- ADR-087: closing a month ----------------
export type MonthClose = {
  month: string;
  ready_on: string;
  ready: boolean;
  closed_at: string | null;
  closed_by: string | null;
  missing: { kind: string; text: string; link: string }[];
  unusual: { group: string; amount: string; average: string }[];
  decided: { rule_id: number; pattern: string; category_path: string; lines: number; is_active: boolean }[];
  invoices: number;
  has_report: boolean;
  sri_url: string;
};
export const fetchClose = (month: string) => send<MonthClose>("GET", `/api/close/${month}`);
export const closeMonth = (month: string) => send<MonthClose>("POST", `/api/close/${month}`);
export const reopenMonth = (month: string) => send<MonthClose>("DELETE", `/api/close/${month}`);

// ---------------- ADR-088: income tax projected for the year ----------------
export type TaxRegime = "employee" | "foreign" | "independent";
export type TaxProfile = { regime: TaxRegime; withheld: string; exempt: string; deductions: string };
export type PersonTax = {
  person: string;
  year: number;
  profile: TaxProfile;
  received: string;
  typical_month: string;
  projected_income: string;
  taxable: string;
  tax: string;
  expenses: string;
  cap: string | null;
  rebate: string;
  room: string;
  more_rebate: string;
  due: string;
  to_pay: string;
  pay_on: string;
  months_left: number;
  set_aside: string;
  notes: string[];
};
export const fetchTaxProjection = (year: number) => send<PersonTax[]>("GET", `/api/taxes/${year}/projection`);
export const saveTaxProfile = (year: number, person: string, body: TaxProfile) =>
  send<PersonTax>("PUT", `/api/taxes/${year}/projection/${person}`, body);

// ---------------- ADR-094: spending by month, split by a dimension ----------------
export type SeriesBy = "none" | "group" | "category" | "person" | "account" | "country";
export type SpendSeries = {
  months: string[];
  by: SeriesBy;
  series: { key: string; label: string; color: string | null; values: string[] }[];
};
export const fetchSpendSeries = (month: string, months: number, by: SeriesBy, person?: string) =>
  send<SpendSeries>("GET", `/api/spending/series${query({ month, months: String(months), by, person })}`);

// ---------- saving (ADR-097) ----------
export type SafeToSpend = {
  month: string;
  left_so_far: Money;
  income_to_come: Money;
  bills_to_come: Money;
  goals_to_go: Money;
  days_left: number;
  amount: Money;
  a_day: Money;
};
export type DebtLine = {
  key: string;
  name: string;
  kind: "card" | "loan";
  balance: Money;
  as_of: string | null;
  rate: string | null; // a year, as a fraction
  minimum: Money | null;
  rate_from: "typed" | "table" | "interest" | null;
  minimum_from: "typed" | "table" | "payment" | "assumed" | null;
  interest_12: Money;
  planned: boolean;
};
export type PayoffPlan = {
  months: number | null;
  interest: Money;
  order: string[];
  paid_in: Record<string, number>;
};
export type Savings = {
  today: string;
  months: {
    month: string;
    money_in: Money;
    spent: Money;
    set_aside: Money;
    kept: Money;
    rate: string | null;
    running: boolean;
  }[];
  rate_12: string | null;
  goals: {
    needed: Money;
    planned: Money;
    saved: Money;
    to_go: Money;
    short: Money;
    goals: {
      goal_id: number;
      name: string;
      target_date: string | null;
      left: Money;
      needed_monthly: Money | null;
      monthly_amount: Money | null;
      status: string;
    }[];
  };
  safe: SafeToSpend;
  debts: DebtLine[];
  payoff: {
    extra: Money;
    minimums: PayoffPlan;
    avalanche: PayoffPlan;
    snowball: PayoffPlan;
    saved: Money;
  } | null;
};
export const fetchSavings = (extra = 0) =>
  send<Savings>("GET", `/api/savings${extra > 0 ? query({ extra }) : ""}`);
export const fetchSafeToSpend = () => send<SafeToSpend>("GET", "/api/savings/safe-to-spend");
export const setDebtTerms = (key: string, body: { rate: string | null; minimum: string | null }) =>
  send<void>("PUT", `/api/savings/debts/${encodeURIComponent(key)}`, body);
