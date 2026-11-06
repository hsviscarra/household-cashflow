import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Flows, Projection } from "../api";
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
const SHEET = {
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
      if (url.startsWith("/api/review")) return json(review);
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
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
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
    expect(await within(strip).findByRole("link", { name: "5 lines to review" })).toHaveAttribute(
      "href",
      "/review",
    );
    expect(
      await within(strip).findByRole("link", { name: "Capital One statement not uploaded" }),
    ).toBeInTheDocument();
    expect(await within(strip).findByRole("link", { name: /Cash runs short on Nov 19/ })).toBeInTheDocument();

    expect(screen.getByText("Money in", { selector: "dt" }).nextSibling).toHaveTextContent("5,000.00");
    expect(screen.getByText("+25% vs Sep")).toBeInTheDocument();
    expect(await screen.findByText("480,000.00")).toBeInTheDocument();
    expect(screen.getByText("Lowest cash ahead", { selector: "dt" }).nextSibling).toHaveTextContent(
      "-120.00",
    );

    expect(screen.getByRole("link", { name: /Groceries/ })).toHaveAttribute(
      "href",
      "/cashflow?month=2026-10&side=out&g=1",
    );
    const coming = screen.getByRole("region", { name: "Coming up, next 14 days" });
    expect(await within(coming).findByText("BIESS mortgage")).toBeInTheDocument();
    expect(within(coming).getByText("3,580.55")).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole("button", { name: "Customize" }));
    const panel = screen.getByRole("region", { name: "Customize Home" });
    fireEvent.click(within(panel).getAllByRole("button", { name: "Hide" })[5]); // Inbox
    await waitFor(() => expect(screen.queryByRole("region", { name: "Inbox" })).not.toBeInTheDocument());
    expect(settings.home).toEqual({ widgets: ["needs", "kpis", "where", "coming", "goals"] });
    fireEvent.click(within(panel).getByRole("button", { name: "Move Goals up" }));
    await waitFor(() =>
      expect(settings.home).toEqual({ widgets: ["needs", "kpis", "where", "goals", "coming"] }),
    );
    fireEvent.click(within(panel).getByRole("button", { name: "Show" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Inbox" })).toBeInTheDocument());
    fireEvent.click(within(panel).getByRole("button", { name: "Back to the default" }));
    await waitFor(() =>
      expect(settings.home).toEqual({ widgets: ["needs", "kpis", "where", "coming", "goals", "inbox"] }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("region", { name: "Customize Home" })).not.toBeInTheDocument();
  });

  it("says when nothing needs you", async () => {
    review = { month: null, uncategorized_lines: 0, suggestions_available: false, groups: [] };
    vi.mocked(fetch).mockImplementation((url, init) => {
      const u = String(url);
      const json = (d: unknown) => Promise.resolve(new Response(JSON.stringify(d)));
      if (u.startsWith("/api/me/settings"))
        return json({ user: "local", settings: { home: { widgets: ["needs", "inbox"] } } });
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
  });
});
