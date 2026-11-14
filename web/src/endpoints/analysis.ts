import { upload } from "./history";
import { query } from "./months";
import { send } from "./settings";

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

/** The same sheet with a trend of `months` months (ADR-101). */
export const fetchBalanceSheetOver = (months: number) =>
  send<BalanceSheet>("GET", `/api/networth${query({ months })}`);

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
