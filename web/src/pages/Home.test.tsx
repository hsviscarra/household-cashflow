import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Flows, MonthMeasures, Projection } from "../api";
import Home, { comingUp } from "./Home";

const FLOWS: Flows = {
  month: "2026-10-01",
  prev_month: "2026-09-01",
  months: ["2026-10-01", "2026-09-01"],
  source: "statements",
  flows: [
    {
      type: "income",
      group_id: 5,
      group_name: "Salary",
      group_color: null,
      category_id: 51,
      category_name: "Hernan",
      amount: "5000",
      prev: "4000",
      transactions: 1,
    },
    {
      type: "expense",
      group_id: 1,
      group_name: "Groceries",
      group_color: "#4E9A2A",
      category_id: 11,
      category_name: "Supermarket",
      amount: "1100",
      prev: "1000",
      transactions: 4,
    },
  ],
  trend: [],
};
const item = (
  day: string,
  name: string,
  amount: string,
  kind: "fixed" | "income" | "purchase" | "variable",
) => ({
  day,
  name,
  amount,
  kind,
});
const PROJECTION: Projection = {
  today: "2026-11-06",
  start_cash: "9000",
  cash_as_of: "2026-11-05",
  variable_per_month: "2000",
  average_months: [],
  months: [
    {
      month: "2026-11-01",
      income: "9000",
      fixed: "4000",
      variable: "2000",
      purchases: "3075.36",
      net: "0",
      end_cash: "9000",
      items: [
        item("2026-11-01", "Past bill", "-50", "fixed"),
        item("2026-11-07", "BIESS mortgage", "-505.19", "fixed"),
        item("2026-11-15", "Salary", "5000", "income"),
        item("2026-11-19", "New house installment", "-3075.36", "purchase"),
        item("2026-11-30", "Too late", "-10", "fixed"),
      ],
    },
  ],
  daily: [],
  lowest: { day: "2026-11-19", balance: "-120.00" },
  next_payday: null,
  alerts: [],
};
const SHEET: { items: Record<string, unknown>[] } & Record<string, unknown> = {
  as_of: "2026-11-05",
  assets: "500000",
  liabilities: "20000",
  net_worth: "480000",
  commitments: "0",
  series: [],
  items: [
    {
      key: "h1",
      name: "New house",
      side: "asset",
      holding_class: "purchase",
      value: "33829",
      as_of: "2026-11-05",
      source: null,
      holding_id: 1,
      account_id: null,
      is_active: true,
      notes: null,
      history: [],
      purchase: {
        target: "83035",
        paid: "33829",
        remaining: "49206",
        installment: "3075.36",
        installments_left: 16,
        full_price: "276782.33",
        at_delivery: "193748",
        lines: "4",
      },
      loan: null,
      category_id: null,
      recurring_template_id: null,
    },
    {
      key: "h2",
      name: "Holding for Rubén",
      side: "liability",
      holding_class: "personal_loan",
      value: "1237.09",
      as_of: "2026-11-05",
      source: null,
      holding_id: 2,
      account_id: null,
      is_active: true,
      notes: null,
      history: [],
      purchase: null,
      loan: null,
      category_id: null,
      recurring_template_id: null,
    },
  ],
};

const period = (
  month: string,
  start: string,
  end: string,
  money_in: string,
  spent: string,
  set_aside: string,
) => ({
  month,
  start,
  end,
  money_in,
  spent,
  set_aside,
  free_cash: String(Number(money_in) - Number(spent)),
  left_over: String(Number(money_in) - Number(spent) - Number(set_aside)),
});
const MEASURES: MonthMeasures = {
  month: "2026-10-01",
  through: "2026-10-31",
  running: false,
  this: period("2026-10-01", "2026-10-01", "2026-10-31", "5000", "1100", "500"),
  before: period("2026-09-01", "2026-09-01", "2026-09-30", "4000", "1000", "500"),
  months: [
    period("2026-09-01", "2026-09-01", "2026-09-30", "4000", "1000", "500"),
    period("2026-10-01", "2026-10-01", "2026-10-31", "5000", "1100", "500"),
  ],
};
SHEET.items.push({
  key: "account-7",
  name: "Banco Pichincha",
  side: "asset",
  holding_class: "cash",
  value: "7954.48",
  as_of: "2026-11-08",
  source: "statement",
  holding_id: null,
  account_id: 7,
  is_active: true,
  notes: null,
  history: [],
  purchase: null,
  loan: null,
  category_id: null,
  recurring_template_id: null,
});

let settings: Record<string, unknown>;
let review: object;

beforeEach(() => {
  settings = {};
  review = {
    month: "2026-10-01",
    uncategorized_lines: 5,
    suggestions_available: true,
    groups: [
      {
        merchant_key: "LUNACORP",
        total: "-40",
        lines: [{}, {}],
        suggestion: {
          category_id: 1,
          category_path: "Personal Care",
          confidence: "0.82",
          reason: "",
          model: "",
        },
      },
    ],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const json = (d: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(d), { status }));
      if (url.startsWith("/api/me/settings")) {
        if (init?.method === "PUT") settings = { ...settings, home: JSON.parse(String(init.body)).value };
        return json({ user: "local", settings });
      }
      if (url.startsWith("/api/cashflow/flows")) return json(FLOWS);
      if (url.startsWith("/api/cashflow/measures")) return json(MEASURES);
      if (url.startsWith("/api/investments/ibkr"))
        return json({
          holding_id: 9,
          as_of: "2026-11-10",
          total: "16440.72",
          cash: "10",
          previous_total: "16300",
          previous_as_of: "2026-11-09",
          stale: false,
          positions: [
            {
              symbol: "VOO",
              description: null,
              asset_class: "ETF",
              currency: "USD",
              quantity: "3",
              price: "690",
              value: "2252.38",
              cost_basis: null,
              unrealized: "446.29",
            },
          ],
        });
      if (url.startsWith("/api/budget/"))
        return json({
          month: "2026-10-01",
          day_share: "1",
          budgeted: "1500",
          spent: "1100",
          unbudgeted: "0",
          left: "400",
          has_plans: true,
          groups: [
            {
              group_id: 1,
              name: "Groceries",
              color: null,
              budget: "1200",
              rollover: false,
              carried: "0",
              spent: "1100",
              available: "1200",
              left: "100",
              expected: "1200",
              status: "on_track",
              suggested: null,
              since: null,
            },
          ],
        });
      if (url.startsWith("/api/review")) return json(review);
      if (url === "/api/todo")
        return json({
          today: "2026-11-06",
          total: 6,
          sections: [
            { key: "categorize", title: "Needs a category", hint: "", tasks: [], count: 5 },
            { key: "books", title: "Statements, imports and bills", hint: "", tasks: [], count: 1 },
          ],
        });
      if (url === "/api/status")
        return json({
          today: "2026-11-06",
          excel_through: null,
          accounts: [],
          loads: [],
          months: [
            {
              month: "2026-10-01",
              source: "statements",
              complete: false,
              coverage: [],
              items: [
                { kind: "statement", text: "Capital One statement not uploaded", link: "/import", count: 1 },
              ],
            },
          ],
        });
      if (url === "/api/projections") return json(PROJECTION);
      if (url === "/api/savings/safe-to-spend")
        return json({
          month: "2026-10-01",
          left_so_far: "2400",
          income_to_come: "0",
          bills_to_come: "1000",
          goals_to_go: "50",
          days_left: 12,
          amount: "1350",
          a_day: "112.50",
        });
      if (url === "/api/networth") return json(SHEET);
      if (url === "/api/people")
        return json([{ counterparty_id: 1, name: "Rubén", holding_id: 2, is_active: true }]);
      return json({ detail: "no" }, 404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={["/?month=2026-10"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Home />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Home", () => {
  it("lists bills from today through the next two weeks", () => {
    expect(comingUp(PROJECTION, "2026-11-06").map((i) => i.name)).toEqual([
      "BIESS mortgage",
      "New house installment",
    ]);
  });

  it("shows what needs you, the numbers, where it went, what's coming, goals and the Inbox", async () => {
    renderHome();
    expect(await screen.findByRole("heading", { level: 1, name: "October 2026" })).toBeInTheDocument();
    const needs = await screen.findByText("Needs you:");
    const strip = needs.parentElement!;
    expect(await within(strip).findByRole("link", { name: "Needs a category: 5" })).toHaveAttribute(
      "href",
      "/todo#categorize",
    );
    expect(
      await within(strip).findByRole("link", { name: "Statements, imports and bills: 1" }),
    ).toBeInTheDocument();
    expect(await within(strip).findByRole("link", { name: /Cash runs short on Nov 19/ })).toBeInTheDocument();

    expect(screen.getByText("Money in", { selector: "dt" }).nextSibling).toHaveTextContent("5,000.00");
    expect(screen.getByRole("button", { name: "Money in: 5,000.00. See the lines" })).toBeInTheDocument();
    expect(screen.getByText("+25% vs Sep: 4,000.00")).toBeInTheDocument();
    expect(screen.getByText("Set aside", { selector: "dt" }).nextSibling).toHaveTextContent("500.00");
    expect(screen.getByText("Left over", { selector: "dt" }).nextSibling).toHaveTextContent("3,400.00");
    expect(screen.getByRole("button", { name: "What is Spent?" })).toBeInTheDocument();
    expect(await screen.findByText("480,000.00")).toBeInTheDocument();
    const now = screen.getByRole("region", { name: "Your money now" });
    expect(within(now).getByText("Banco Pichincha")).toBeInTheDocument();
    expect(within(now).getByText("statement Nov 8")).toBeInTheDocument();
    const inv = screen.getByRole("region", { name: "Investments" });
    expect(await within(inv).findByText("16,440.72")).toBeInTheDocument();
    expect(within(inv).getByText("VOO")).toBeInTheDocument();
    const budget = screen.getByRole("region", { name: "Budget: planned vs actual" });
    expect(await within(budget).findByText("Groceries")).toBeInTheDocument();

    expect(screen.getByRole("button", { name: /Groceries/ })).toBeInTheDocument();
    const coming = screen.getByRole("region", { name: "Coming up, next 14 days" });
    expect(await within(coming).findByText("BIESS mortgage")).toBeInTheDocument();
    expect(within(coming).getByText("3,580.55")).toBeInTheDocument();
    expect(within(coming).getByText("-120.00")).toBeInTheDocument();
    const goals = screen.getByRole("region", { name: "Goals" });
    expect(await within(goals).findByText("Held for Rubén")).toBeInTheDocument();
    expect(within(goals).getByRole("progressbar", { name: "New house: paid" })).toHaveAttribute(
      "aria-valuenow",
      "41",
    );
    expect(within(goals).getByText("16 × 3,075.36 left")).toBeInTheDocument();
    const inbox = screen.getByRole("region", { name: "Inbox" });
    expect(await within(inbox).findByText("Claude: Personal Care · 82%")).toBeInTheDocument();
  });

  it("hides, reorders and restores widgets for the person", async () => {
    renderHome();
    await screen.findByRole("heading", { level: 1, name: "October 2026" });
    await screen.findByText("Money in", { selector: "dt" });
    fireEvent.click(screen.getByRole("button", { name: "Customize" }));
    const panel = screen.getByRole("region", { name: "Customize Home" });
    const all = [
      "needs",
      "kpis",
      "safe",
      "money",
      "networth",
      "cashflow",
      "investments",
      "budget",
      "goals",
      "coming",
      "where",
      "inbox",
    ];
    // Safe to spend (ADR-097): the month running now, with how it was reached.
    const safe = screen.getByRole("region", { name: "Safe to spend" });
    expect(await within(safe).findByLabelText("Safe to spend")).toHaveTextContent("1,350.00");
    expect(safe).toHaveTextContent("about 112.50 a day for 12 days");
    expect(safe).toHaveTextContent("Bills still due this month−1,000.00");

    fireEvent.click(within(panel).getAllByRole("button", { name: "Hide" })[11]); // Inbox
    await waitFor(() => expect(screen.queryByRole("region", { name: "Inbox" })).not.toBeInTheDocument());
    expect(settings.home).toEqual({ widgets: all.slice(0, 11), layout: 2, known: all });
    fireEvent.click(within(panel).getByRole("button", { name: "Move Coming up up" }));
    await waitFor(() =>
      expect(settings.home).toEqual({
        widgets: [
          "needs",
          "kpis",
          "safe",
          "money",
          "networth",
          "cashflow",
          "investments",
          "budget",
          "coming",
          "goals",
          "where",
        ],
        layout: 2,
        known: all,
      }),
    );
    fireEvent.click(within(panel).getByRole("button", { name: "Show" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Inbox" })).toBeInTheDocument());
    fireEvent.click(within(panel).getByRole("button", { name: "Back to the default" }));
    await waitFor(() => expect(settings.home).toEqual({ widgets: all, layout: 2, known: all }));
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("region", { name: "Customize Home" })).not.toBeInTheDocument();
  });

  it("says when nothing needs you", async () => {
    review = { month: null, uncategorized_lines: 0, suggestions_available: false, groups: [] };
    vi.mocked(fetch).mockImplementation((url, init) => {
      const u = String(url);
      const json = (d: unknown) => Promise.resolve(new Response(JSON.stringify(d)));
      if (u.startsWith("/api/me/settings"))
        return json({ user: "local", settings: { home: { widgets: ["needs", "inbox"], layout: 2 } } });
      if (u.startsWith("/api/cashflow/flows")) return json(FLOWS);
      if (u.startsWith("/api/review")) return json(review);
      if (u === "/api/status") return json({ months: [] });
      if (u === "/api/projections") return json({ ...PROJECTION, lowest: null });
      void init;
      return json({});
    });
    renderHome();
    expect(await screen.findByText("Nothing needs you.")).toBeInTheDocument();
    expect(await screen.findByText("Every line has a category.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Goals" })).not.toBeInTheDocument();
    // A widget added after this list was saved shows up once, after the first two.
    expect(screen.getByRole("region", { name: "Safe to spend" })).toBeInTheDocument();
  });
});
