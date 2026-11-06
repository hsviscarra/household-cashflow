import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Flow, FlowLine, Flows } from "../api";
import { fold } from "../components/flowcharts";
import CashFlowPage, { drillOf, rows, steps } from "./CashFlow";

const flow = (p: Partial<Flow>): Flow => ({
  type: "expense",
  group_id: 1,
  group_name: "Groceries",
  group_color: "#4E9A2A",
  category_id: 11,
  category_name: "Supermarket",
  amount: "0",
  prev: "0",
  transactions: 1,
  ...p,
});
const FLOWS: Flows = {
  month: "2026-10-01",
  prev_month: "2026-09-01",
  months: ["2026-10-01", "2026-09-01"],
  source: "statements",
  flows: [
    flow({
      type: "income",
      group_id: 5,
      group_name: "Salary",
      category_id: 51,
      category_name: "Hernan",
      amount: "5200",
      prev: "5000",
    }),
    flow({
      type: "income",
      group_id: 5,
      group_name: "Salary",
      category_id: 52,
      category_name: "Lauren",
      amount: "4000",
      prev: "3000",
    }),
    flow({ amount: "300", prev: "250", transactions: 3 }),
    flow({ category_id: 12, category_name: "Grocery Delivery", amount: "100", prev: "0" }),
    flow({
      group_id: 2,
      group_name: "Dining",
      category_id: 21,
      category_name: "Restaurants",
      amount: "400",
      prev: "600",
    }),
    flow({
      type: "savings",
      group_id: 7,
      group_name: "Savings & Debt",
      category_id: 71,
      category_name: "Investing",
      amount: "1000",
      prev: "1000",
    }),
  ],
  trend: [
    { month: "2026-09-01", money_in: "8000", money_out: "1850" },
    { month: "2026-10-01", money_in: "9200", money_out: "1800" },
  ],
};
const line = (p: Partial<FlowLine>): FlowLine => ({
  transaction_id: 1,
  txn_date: "2026-10-03",
  description: "SUPERMAXI QUITO 1",
  merchant: "SUPERMAXI",
  amount: "-120.00",
  type: "expense",
  category_name: "Supermarket",
  account_name: "Produbanco Hernan",
  person: "Hernan",
  source: "statement",
  notes: null,
  ...p,
});
const LINES = [
  line({}),
  line({ transaction_id: 2, description: "SUPERMAXI QUITO 2", amount: "-100.00" }),
  line({
    transaction_id: 3,
    description: "MEGAMAXI",
    merchant: "MEGAMAXI",
    amount: "-80.00",
    person: "Lauren",
  }),
];

let urls: string[];
let lines: FlowLine[];

beforeEach(() => {
  urls = [];
  lines = LINES;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      urls.push(url);
      const json = (d: unknown) => Promise.resolve(new Response(JSON.stringify(d)));
      if (url.startsWith("/api/me/settings")) return json({ user: "local", settings: {} });
      if (url.startsWith("/api/cashflow/flows")) return json(FLOWS);
      if (url.startsWith("/api/cashflow/lines")) return json(lines);
      return json([]);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function Where() {
  const { search } = useLocation();
  return <output aria-label="search">{search}</output>;
}

function renderAt(path = "/cashflow") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Where />
        <CashFlowPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("cash flow helpers", () => {
  it("groups money in by category and money out by group, savings by category", () => {
    const r = rows(FLOWS.flows);
    expect(r.map((x) => [x.key, x.label, x.amount])).toEqual([
      ["in:c51", "Salary Hernan", 5200],
      ["in:c52", "Salary Lauren", 4000],
      ["out:g1", "Groceries", 400],
      ["out:g2", "Dining", 400],
      ["out:c71", "Investing", 1000],
    ]);
    expect(drillOf("out:g1")).toEqual({ side: "out", group: 1 });
    expect(drillOf("in:c52")).toEqual({ side: "in", category: 52 });
  });

  it("keeps the biggest changes and folds the rest", () => {
    const r = rows(FLOWS.flows).filter((x) => x.side === "out");
    expect(steps(r)).toEqual([
      { key: "out:g2", label: "Dining", change: -200 },
      { key: "out:g1", label: "Groceries", change: 150 },
    ]);
    expect(steps(r, 1)).toEqual([{ key: "rest", label: "Everything else", change: -50 }]);
    const nodes = Array.from({ length: 12 }, (_, i) => ({ key: `k${i}`, label: `N${i}`, amount: 12 - i }));
    const folded = fold(nodes);
    expect(folded).toHaveLength(9);
    expect(folded[8]).toEqual({ key: "other", label: "Other (4)", amount: 4 + 3 + 2 + 1 });
    expect(fold([{ key: "a", label: "A", amount: 0 }])).toEqual([]);
  });
});

describe("Cash flow page", () => {
  it("shows the month as a Sankey and a waterfall, and drills down to lines", async () => {
    renderAt("/cashflow?month=2026-10");
    expect(
      await screen.findByRole("heading", { name: /October 2026: where 9,200.00 came from and went/ }),
    ).toBeInTheDocument();
    expect(urls).toContain("/api/cashflow/flows?month=2026-10-01");
    expect(screen.getByText(/Kept/)).toHaveTextContent("Kept 7,400.00.");
    expect(
      screen.getByRole("heading", { name: "Why Oct’s spending was lower than Sep’s" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Money in" }));
    expect(
      screen.getByRole("heading", { name: "Why Oct’s income was higher than Sep’s" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Salary Lauren" })).toBeInTheDocument();

    // Band → group → category → merchant → lines, and back up the path.
    fireEvent.click(screen.getByRole("button", { name: "Groceries 400.00: open" }));
    expect(screen.getByRole("status", { name: "search" })).toHaveTextContent("side=out&g=1");
    const group = screen.getByRole("region", { name: "Groceries by category" });
    fireEvent.click(within(group).getByRole("button", { name: "Supermarket" }));
    const cat = await screen.findByRole("region", { name: "Supermarket by merchant" });
    await waitFor(() =>
      expect(urls).toContain("/api/cashflow/lines?month=2026-10-01&side=out&category_id=11"),
    );
    expect(within(cat).getByText("2 lines · 220.00")).toBeInTheDocument();
    fireEvent.click(within(cat).getByRole("button", { name: "SUPERMAXI" }));
    const merchant = screen.getByRole("region", { name: "SUPERMAXI" });
    expect(within(merchant).getAllByRole("row")).toHaveLength(3);
    const path = screen.getByRole("navigation", { name: "Drill path" });
    expect(within(path).getByText("SUPERMAXI")).toHaveAttribute("aria-current", "location");
    fireEvent.click(within(path).getByRole("button", { name: "Money out" }));
    expect(screen.getByRole("region", { name: "Money out by category" })).toBeInTheDocument();
    fireEvent.click(within(path).getByRole("button", { name: "October 2026" }));
    expect(screen.queryByRole("region", { name: "Money out by category" })).not.toBeInTheDocument();
  });

  it("says when a category comes from the workbook, and picks a month from the bars", async () => {
    lines = [
      line({
        description: "Supermarket",
        merchant: null,
        source: "excel_history",
        account_name: null,
        person: null,
      }),
    ];
    renderAt("/cashflow?month=2026-10&side=out&c=11");
    expect(await screen.findByText(/One amount per category from the/)).toBeInTheDocument();
    expect(screen.getByText("Workbook")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sep" }));
    expect(screen.getByRole("status", { name: "search" })).toHaveTextContent("?month=2026-09");
  });
});
