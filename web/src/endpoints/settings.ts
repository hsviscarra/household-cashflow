import { type Money } from "./history";

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

export async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
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
