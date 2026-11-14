import { type Money } from "./history";
import { query } from "./months";
import { send } from "./settings";

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
  rate_from: "typed" | "table" | null;
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

// ---------- net worth, years ahead (ADR-098) ----------
export type AheadYear = {
  year: number;
  end: string;
  cash: Money;
  investments_low: Money;
  investments: Money;
  investments_high: Money;
  property: Money;
  vehicles: Money;
  other_assets: Money;
  loans: Money;
  other_debts: Money;
  kept: Money;
  net_low: Money;
  net: Money;
  net_high: Money;
  milestones: string[];
};

export type Ahead = {
  today: string;
  kept_a_year: Money;
  net_today: Money;
  loans: { name: string; balance: Money; from_table: boolean; paid_off: string | null }[];
  years: AheadYear[];
};

/** Yearly rates as fractions (0.05 is 5%); what is left out takes the server's default. */
export type AheadChoices = {
  years: number;
  low: number;
  expected: number;
  high: number;
  property_growth: number;
  vehicle_growth: number;
  invest_share: number;
};

export const DEFAULT_AHEAD: AheadChoices = {
  years: 5,
  low: 0.02,
  expected: 0.05,
  high: 0.08,
  property_growth: 0,
  vehicle_growth: -0.1,
  invest_share: 0,
};

export const fetchAhead = (c: AheadChoices = DEFAULT_AHEAD) =>
  send<Ahead>("GET", `/api/networth/ahead${query(c)}`);

// ---------- explore (ADR-099) ----------
export type ExploreMeasure = "amount" | "lines" | "average";

export type ExploreDimension =
  "month" | "year" | "group" | "category" | "person" | "account" | "country" | "merchant" | "kind";

export type ExploreResult = {
  measure: ExploreMeasure;
  rows_by: ExploreDimension;
  cols_by: ExploreDimension | null;
  rows: string[];
  cols: string[];
  cells: Money[][];
  row_totals: Money[];
  col_totals: Money[];
  total: Money;
  folded: number;
};

export const fetchExplore = (q: {
  start: string;
  end: string;
  rows: ExploreDimension;
  cols?: ExploreDimension | null;
  measure: ExploreMeasure;
  person?: string | null;
  group_id?: number | null;
}) => send<ExploreResult>("GET", `/api/explore${query(q)}`);

// ---------- ask Claude (ADR-100) ----------
export type AskUsage = {
  available: boolean;
  month: string;
  spent: Money;
  questions: number;
  cap: Money;
  left: Money;
};

export type AskAnswer = { answer: string; cost: Money; tools_used: string[]; usage: AskUsage };

export const fetchAskUsage = () => send<AskUsage>("GET", "/api/ask/usage");

export const askClaude = (body: { question: string; page?: string; month?: string; deep?: boolean }) =>
  send<AskAnswer>("POST", "/api/ask", body);

export const setAskCap = (cap: number) => send<AskUsage>("PUT", "/api/ask/cap", { cap: cap.toFixed(2) });
