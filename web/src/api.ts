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
};
export type RuleInput = Pick<Rule, "pattern" | "match_type" | "category_id" | "priority">;

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
export const testRule = (description: string) =>
  send<{ description: string; rule: Rule | null }>(
    "GET",
    `/api/merchant-rules/test?description=${encodeURIComponent(description)}`,
  );
