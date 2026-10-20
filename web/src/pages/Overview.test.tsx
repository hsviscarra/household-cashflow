import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Overview from "./Overview";

const month = (
  m: string,
  income: string,
  expenses: string,
  savings: string,
  debt: string,
  net: string,
  cum: string,
) => ({
  cash_month: m,
  income,
  expenses,
  savings,
  debt_payments: debt,
  net,
  cumulative_net: cum,
  savings_rate: null,
  transactions: 3,
});

const MONTHLY = [
  month("2025-12-01", "7000", "2000", "0", "1500", "3500", "3500"),
  month("2026-01-01", "8800", "4400", "900", "4000", "-500", "3000"),
  month("2026-02-01", "9200", "3900", "900", "3000", "1400", "4400"),
];
const CATS = [
  {
    cash_month: "2026-01-01",
    type: "income",
    group_id: 1,
    group_name: "Salary",
    group_color: "#4E9A2A",
    category_id: 2,
    category_name: "Hernan",
    amount: "5000",
    transactions: 1,
  },
  {
    cash_month: "2026-01-01",
    type: "income",
    group_id: 1,
    group_name: "Salary",
    group_color: "#4E9A2A",
    category_id: 3,
    category_name: "Lauren",
    amount: "3200",
    transactions: 1,
  },
  {
    cash_month: "2026-02-01",
    type: "expense",
    group_id: 9,
    group_name: "Housing",
    group_color: "#6B6788",
    category_id: 10,
    category_name: "Condo Fee",
    amount: "250",
    transactions: 1,
  },
  {
    cash_month: "2026-01-01",
    type: "debt_payment",
    group_id: 30,
    group_name: "Transfers",
    group_color: null,
    category_id: 31,
    category_name: "Card Payment",
    amount: "4000",
    transactions: 1,
  },
];
const PLAN = [
  { month: "2026-02-01", income: "1", outflows: "1" }, // has actuals: the plan is dropped
  { month: "2026-07-01", income: "5600", outflows: "2700" },
];

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const body = url.includes("/monthly") ? MONTHLY : url.includes("/plan") ? PLAN : CATS;
      return Promise.resolve(new Response(JSON.stringify(body)));
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderAt(path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Overview />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Overview", () => {
  it("leads with the latest year in a sentence and shows the tiles", async () => {
    renderAt();
    const h1 = await screen.findByRole("heading", { level: 1 });
    expect(h1).toHaveTextContent("In Jan–Feb 2026 you kept 900.00 of 18,000.00.");
    expect(screen.getByText("Money in", { selector: "dt" }).nextSibling).toHaveTextContent("18,000.00");
    expect(screen.getByText("Share kept", { selector: "dt" }).nextSibling).toHaveTextContent("5%");
    expect(screen.getByRole("button", { name: "2026" })).toHaveAttribute("aria-pressed", "true");
  });

  it("switches year and says when more went out than came in", async () => {
    renderAt("/?year=2025");
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "In December 2025 you kept 3,500.00 of 7,000.00.",
    );
    fireEvent.click(screen.getByRole("button", { name: "2026" }));
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("you kept 900.00");
  });

  it("draws months, the plan and a hover tooltip", async () => {
    renderAt();
    await screen.findByRole("img", { name: "Money in and out by month, 2026" });
    expect(screen.getByText("Plan")).toBeInTheDocument();
    fireEvent.mouseEnter(screen.getByTestId("col-2026-07-01"));
    expect(screen.getByRole("status")).toHaveTextContent("July 2026 (plan)");
    fireEvent.mouseEnter(screen.getByTestId("col-2026-02-01"));
    expect(screen.getByRole("status")).toHaveTextContent("February 2026In9,200.00");
    fireEvent.mouseEnter(screen.getByTestId("col-2026-01-01"));
    expect(screen.getByRole("status")).toHaveTextContent("Kept-500.00");
  });

  it("breaks the year down by category group", async () => {
    renderAt();
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("rowheader", { name: "Salary" }).closest("tr")).toHaveTextContent(
      "8,200.00",
    );
    expect(within(table).getByText("Card and loan payments")).toBeInTheDocument();
    expect(within(table).getByRole("rowheader", { name: "Card Payment" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Feb" })).toBeInTheDocument();
  });
});
