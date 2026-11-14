import { type Money } from "./history";
import { type Txn } from "./imports";
import { send } from "./settings";

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

export const query = (o: Record<string, string | number | undefined | null>) => {
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
