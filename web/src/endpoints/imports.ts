import { type Money, type Statement } from "./history";
import { type MatchType, type Owner, send } from "./settings";

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

export const monthQuery = (month?: string | null) => (month ? `?month=${month}` : "");

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
