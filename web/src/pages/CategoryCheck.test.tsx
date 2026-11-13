import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CategoryCheckPage from "./CategoryCheck";

const line = (id: number, path: string | null, type: string, amount: string, description: string) => ({
  transaction_id: id,
  txn_date: `2026-10-0${id}`,
  post_date: null,
  cash_month: "2026-10-01",
  account_id: 1,
  account_name: "Produbanco",
  description,
  merchant: null,
  amount,
  type,
  category_id: path ? id : null,
  category_path: path,
  person: null,
  country: "EC",
  source: "statement",
  statement_file_id: null,
  notes: null,
  category_source: null,
  parent_transaction_id: null,
  parts: 0,
});
const LINES = [
  line(1, "Groceries / Supermarket", "expense", "-50.00", "SUPERMAXI"),
  line(2, "Groceries / Supermarket", "expense", "-20.00", "FARMACIA"),
  line(3, "Salaries / Hernan", "income", "5000.00", "KENILITY"),
  line(4, null, "expense", "-9.00", "UNKNOWN SHOP"),
];
const CATS = [
  {
    category_id: 10,
    name: "Health",
    kind: "expense",
    color: null,
    is_fixed: false,
    sort_order: 1,
    children: [
      {
        category_id: 11,
        name: "Pharmacy",
        kind: "expense",
        color: null,
        is_fixed: false,
        sort_order: 1,
        children: [],
      },
    ],
  },
];

let calls: { method: string; url: string; body: unknown }[];
beforeEach(() => {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : null });
      const json = (d: unknown) => Promise.resolve(new Response(JSON.stringify(d), { status: 200 }));
      if (url.startsWith("/api/categories")) return json(CATS);
      if (method === "PATCH") return json(LINES[1]);
      return json(LINES);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("By category", () => {
  it("lists every kind of category and moves a line", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/transactions/categories?month=2026-10&c=Groceries / Supermarket"]}>
          <CategoryCheckPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const nav = await screen.findByRole("navigation", { name: "Categories" });
    expect(within(nav).getByText("No category yet")).toBeInTheDocument();
    expect(within(nav).getByText("Salaries / Hernan")).toBeInTheDocument();
    const box = screen.getByRole("region", { name: "Groceries / Supermarket" });
    expect(box).toHaveTextContent(/2 lines · .?70\.00/);
    fireEvent.click(within(box).getByLabelText("Tick FARMACIA"));
    expect(within(box).getByText("Move 1 ticked to")).toBeInTheDocument();
    // The lines are on the shared table (ADR-091): a totals row, and columns to add.
    const table = within(box).getByRole("table", { name: "Lines in Groceries / Supermarket" });
    expect(within(table).getAllByRole("row").at(-1)).toHaveTextContent(/Total · 2.*70\.00/);
    expect(within(box).getByLabelText("Group by")).toBeInTheDocument();
    expect(within(box).getByLabelText("Counts in")).not.toBeChecked();
  });
});
