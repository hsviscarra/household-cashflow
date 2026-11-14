import { type Money } from "./history";
import { type InvoiceUpload } from "./invoices";
import { query } from "./months";
import { type TemplateType } from "./recurring";
import { send } from "./settings";

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
