import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Debt, Subscriptions } from "../api";
import DebtPage, { debtHeadline, monthTotals } from "./Debt";
import SubscriptionsPage from "./Subscriptions";

const charge = (id: number, d: string, amount: string) => ({
  transaction_id: id,
  txn_date: d,
  amount,
  description: "GOOGLE *Sample App M",
  account_name: "Card",
});
const SUBS: Subscriptions = {
  monthly_cost: "56.28",
  weekly_monthly_cost: "43.29",
  subscriptions: [
    {
      merchant: "GOOGLE *SAMPLE APP M",
      cadence: "weekly",
      typical: "9.99",
      monthly_cost: "43.29",
      yearly_cost: "519.48",
      category_path: "Subscriptions & Software / Apps",
      accounts: ["Card"],
      charges: [charge(1, "2026-09-01", "9.99"), charge(2, "2026-09-08", "9.99")],
      last: "2026-09-08",
      next_expected: "2026-09-15",
      active: true,
    },
    {
      merchant: "STREAMFLIX",
      cadence: "monthly",
      typical: "12.99",
      monthly_cost: "12.99",
      yearly_cost: "155.88",
      category_path: null,
      accounts: [],
      charges: [charge(3, "2026-07-15", "12.99"), charge(4, "2026-08-14", "12.99")],
      last: "2026-08-14",
      next_expected: "2026-09-13",
      active: false,
    },
    {
      merchant: "BETTERFIT APP",
      cadence: "possible",
      typical: "80.00",
      monthly_cost: "80.00",
      yearly_cost: "960.00",
      category_path: "Subscriptions & Software / Apps",
      accounts: ["Other card"],
      charges: [charge(5, "2026-09-01", "80.00")],
      last: "2026-09-01",
      next_expected: null,
      active: true,
    },
  ],
};
// November 2025 to October 2026.
const MONTHS = Array.from({ length: 12 }, (_, i) =>
  i < 2 ? `2025-${11 + i}-01` : `2026-${String(i - 1).padStart(2, "0")}-01`,
);
const DEBT: Debt = {
  year: 2026,
  years: [2026, 2025],
  through: "2026-10-01",
  months: MONTHS,
  interest: "52.50",
  fees: "4.00",
  accounts: [
    {
      account_id: 1,
      name: "Capital One Venture",
      kind: "credit_card",
      interest: "42.50",
      fees: "0",
      total: "42.50",
      last_12: "42.50",
      by_category: { "Credit Card Interest": "42.50" },
      by_month: { "2026-10-01": "42.50" },
      balance: "1234.56",
      balance_date: "2026-10-03",
    },
    {
      account_id: 2,
      name: "Bank",
      kind: "checking",
      interest: "10",
      fees: "4",
      total: "14",
      last_12: "14",
      by_category: {},
      by_month: {},
      balance: null,
      balance_date: null,
    },
  ],
};

const EMPTY_SHEET = {
  as_of: "2026-10-27",
  assets: "0",
  liabilities: "0",
  net_worth: "0",
  commitments: "0",
  items: [],
  series: [{ month: "2026-10-01", assets: "0", liabilities: "0", net: "0" }],
};
let urls: string[];
function renderWith(page: ReactElement, body: unknown, path = "/", status = 200) {
  urls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      urls.push(url);
      if (url === "/api/networth") return Promise.resolve(new Response(JSON.stringify(EMPTY_SHEET)));
      if (url === "/api/investments/ibkr")
        return Promise.resolve(
          new Response(
            JSON.stringify({
              holding_id: null,
              as_of: null,
              total: null,
              cash: null,
              previous_total: null,
              previous_as_of: null,
              stale: false,
              positions: [],
            }),
          ),
        );
      return Promise.resolve(new Response(JSON.stringify(body), { status }));
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        {page}
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("Subscriptions page", () => {
  it("totals active subscriptions and groups them by cadence", async () => {
    renderWith(<SubscriptionsPage />, SUBS);
    expect(
      await screen.findByRole("heading", { level: 1, name: "1 subscriptions cost 56.28 a month" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Weekly app billing, a month").nextSibling).toHaveTextContent("43.29");
    expect(screen.getByText("Each year").nextSibling).toHaveTextContent("675.36");
    const weekly = screen.getByRole("list", { name: "Weekly" });
    expect(weekly).toHaveTextContent("43.29 a month · 519.48 a year");
    expect(weekly).toHaveTextContent("Active");
    expect(weekly).toHaveTextContent(/next about Sep 15, 2026/);
    fireEvent.click(within(weekly).getByRole("button", { name: /GOOGLE \*SAMPLE APP M/ }));
    expect(screen.getByRole("list", { name: "Charges of GOOGLE *SAMPLE APP M" }).children).toHaveLength(2);
    expect(screen.getByRole("list", { name: "Monthly" })).toHaveTextContent("Stopped?");
    const possible = screen.getByRole("list", { name: "Possible subscriptions" });
    expect(possible).toHaveTextContent("80.00");
    expect(possible).not.toHaveTextContent("a month");
  });

  it("says when nothing repeats and on errors", async () => {
    const { unmount } = renderWith(<SubscriptionsPage />, { ...SUBS, subscriptions: [] });
    expect(await screen.findByText(/No repeating charges found yet/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Subscriptions");
    unmount();
    renderWith(<SubscriptionsPage />, { detail: "boom" }, "/", 500);
    expect(await screen.findByText("Could not load subscriptions: boom")).toBeInTheDocument();
  });
});

describe("Debt page", () => {
  it("states the year's interest and fees and breaks them down per account", async () => {
    expect(monthTotals(DEBT).at(-1)).toBe(42.5);
    expect(debtHeadline({ ...DEBT, interest: "0", fees: "0", through: "2019-12-01", year: 2019 })).toBe(
      "2019: no interest or fees",
    );
    renderWith(<DebtPage />, DEBT, "/debt");
    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: /2026( so far)?: 52.50 in interest and 4.00 in fees/,
      }),
    ).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Interest and fees by account, 2026" });
    const co = within(table).getByRole("row", { name: /Capital One Venture/ });
    expect(co).toHaveTextContent("42.50");
    expect(co).toHaveTextContent("1,234.56");
    expect(co).toHaveTextContent("on Oct 3, 2026");
    fireEvent.click(within(table).getByRole("button", { name: /Capital One Venture/ }));
    expect(screen.getByRole("list", { name: "Capital One Venture: 2026 by kind" })).toHaveTextContent(
      "Credit Card Interest42.50",
    );
    expect(screen.getByRole("list", { name: "Capital One Venture: by month" })).toHaveTextContent(
      "October 2026",
    );
    fireEvent.click(within(table).getByRole("button", { name: /Bank/ }));
    expect(screen.getByText("None this year.")).toBeInTheDocument();
    expect(screen.getByText("None in the last 12 months.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /^Interest and fees by month/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "2025" }));
    expect(urls).toContain("/api/debt?year=2025");
  });

  it("says when there is nothing and on errors", async () => {
    const { unmount } = renderWith(<DebtPage />, { ...DEBT, accounts: [] });
    expect(await screen.findByText("No interest or fees loaded.")).toBeInTheDocument();
    unmount();
    renderWith(<DebtPage />, { detail: "boom" }, "/", 500);
    expect(await screen.findByText("Could not load the cost of debt: boom")).toBeInTheDocument();
  });
});
