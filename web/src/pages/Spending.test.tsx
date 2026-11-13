import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Spending } from "../api";
import SpendingPage, { change, compareWords, headline } from "./Spending";

const MONTHS = Array.from({ length: 12 }, (_, i) => `2026-${String(i + 1).padStart(2, "0")}-01`).reverse();
const SPENDING: Spending = {
  month: "2026-09-01",
  months: ["2026-10-01", "2026-09-01", "2026-08-01"],
  source: "statements",
  total: { amount: "1100", prev: "1000", last_year: "1250", transactions: 9 },
  groups: [
    {
      group_id: 1,
      name: "Groceries",
      color: "#4E9A2A",
      amount: "600",
      prev: "500",
      last_year: "0",
      transactions: 5,
      categories: [
        { category_id: 11, name: "Supermarket", amount: "550", prev: "500", last_year: "0", transactions: 4 },
        {
          category_id: 12,
          name: "Grocery Delivery",
          amount: "50",
          prev: "0",
          last_year: "0",
          transactions: 1,
        },
      ],
    },
    {
      group_id: 2,
      name: "Dining",
      color: null,
      amount: "500",
      prev: "500",
      last_year: "1250",
      transactions: 4,
      categories: [
        {
          category_id: 21,
          name: "Restaurants",
          amount: "500",
          prev: "500",
          last_year: "1250",
          transactions: 4,
        },
      ],
    },
  ],
  by_person: [
    { key: "Hernan", amount: "800", transactions: 6 },
    { key: "Joint", amount: "300", transactions: 3 },
  ],
  by_country: [{ key: "EC", amount: "1100", transactions: 9 }],
  fixed: [
    { key: "variable", amount: "1000", transactions: 8 },
    { key: "fixed", amount: "100", transactions: 1 },
  ],
  merchants: [{ merchant: "SUPERMAXI", group_name: "Groceries", amount: "400", transactions: 3 }],
  trend: [...MONTHS].reverse().map((m) => ({ month: m, amount: m === "2026-09-01" ? "1100" : "900" })),
};
const LINES = [
  {
    transaction_id: 1,
    txn_date: "2026-09-04",
    merchant: "SUPERMAXI",
    description: "SUPERMAXI SAMPLE STORE",
    amount: "200.00",
    category_name: "Supermarket",
    group_name: "Groceries",
    person: "Hernan",
    account_name: "Card",
    source: "statement",
  },
  {
    transaction_id: 2,
    txn_date: "2026-09-20",
    merchant: "SUPERMAXI",
    description: "SUPERMAXI DEVOLUCION",
    amount: "-10.00",
    category_name: "Supermarket",
    group_name: "Groceries",
    person: "Joint",
    account_name: null,
    source: "manual",
  },
];
let urls: string[];
let settings: Record<string, unknown>;
let body: unknown;

beforeEach(() => {
  urls = [];
  settings = {};
  body = SPENDING;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/me/settings")) {
        if (init?.method === "PUT")
          settings = { ...settings, ...{ person: JSON.parse(String(init.body)).value } };
        return Promise.resolve(new Response(JSON.stringify({ user: "local", settings })));
      }
      if (url.startsWith("/api/spending/series"))
        return Promise.resolve(
          new Response(
            JSON.stringify({
              months: SPENDING.trend.map((t) => t.month),
              by: "none",
              series: [
                {
                  key: "Spending",
                  label: "Spending",
                  color: null,
                  values: SPENDING.trend.map((t) => t.amount),
                },
              ],
            }),
          ),
        );
      urls.push(url);
      const out = url.startsWith("/api/spending/lines")
        ? LINES
        : url.startsWith("/api/spending/merchants")
          ? MERCHANTS
          : url.startsWith("/api/spending/products")
            ? PRODUCTS
            : url.startsWith("/api/spending/ideas")
              ? IDEAS
              : body;
      return Promise.resolve(new Response(JSON.stringify(out)));
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const MERCHANTS = [
  {
    merchant: "SUPERMAXI",
    group_id: 1,
    group_name: "Groceries",
    amount: "300.00",
    visits: 3,
    avg_ticket: "100.00",
    invoices: 2,
  },
  {
    merchant: "RAPPI",
    group_id: 1,
    group_name: "Groceries",
    amount: "40.00",
    visits: 2,
    avg_ticket: "20.00",
    invoices: 0,
  },
];
const PRODUCTS = [
  {
    product_key: "LECHE",
    description: "Leche 1L",
    product_group: "Dairy & Eggs",
    times: 3,
    quantity: "3",
    amount: "3.30",
    unit_price: "1.10",
    before: "0.95",
    change: "0.1579",
    stores: ["SUPERMAXI"],
    cheaper_store: "AKI",
    cheaper_price: "0.80",
    could_save: "0.90",
  },
  {
    product_key: "PAN",
    description: "Pan",
    product_group: null,
    times: 1,
    quantity: "1",
    amount: "2.00",
    unit_price: "2.00",
    before: null,
    change: null,
    stores: ["SUPERMAXI"],
    cheaper_store: null,
    cheaper_price: null,
    could_save: "0",
  },
];
const IDEAS = [
  {
    key: "delivery",
    title: "Delivery apps: 2 orders",
    detail: "RAPPI.",
    amount: "40.00",
    count: 2,
    link: "/spending?month=2026-09&view=merchants",
  },
];

function renderAt(path = "/spending") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <SpendingPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("spending helpers", () => {
  it("describes changes in words and numbers", () => {
    expect(change("1100", "1000")).toBe("+10% (+100.00)");
    expect(change("900", "1000")).toBe("−10% (−100.00)");
    expect(change("5", "0")).toBe("new");
    expect(change("0", "0")).toBe("—");
    expect(compareWords("1100", "1000", "August")).toBe("10% more than August");
    expect(compareWords("1000", "1003", "August")).toBe("about the same as August");
    expect(compareWords("1", "0", "August")).toBeNull();
    expect(headline(SPENDING)).toBe(
      "In September 2026 you spent 1,100.00: 10% more than August, 12% less than September 2025.",
    );
    expect(headline({ ...SPENDING, source: "none" })).toBe("Spending");
    expect(
      headline({ ...SPENDING, month: "2026-01-01", total: { ...SPENDING.total, prev: "0", last_year: "0" } }),
    ).toBe("In January 2026 you spent 1,100.00.");
    // A month that isn't over isn't compared with whole months.
    expect(headline({ ...SPENDING, month: "2026-11-01" }, "2026-11-09")).toBe(
      "So far in November 2026 (day 9) you spent 1,100.00.",
    );
  });
});

describe("Spending page", () => {
  it("leads with the month, compares it and drills from group to lines", async () => {
    renderAt("/spending?month=2026-09");
    expect(
      await screen.findByRole("heading", { level: 1, name: /^In September 2026 you spent 1,100.00/ }),
    ).toBeInTheDocument();
    expect(urls[0]).toBe("/api/spending?month=2026-09-01");
    const table = screen.getByRole("table", { name: "Spending by category in September 2026" });
    const groceries = within(table).getByRole("button", { name: /Groceries/ });
    expect(groceries).toHaveAttribute("aria-expanded", "false");
    expect(within(table).getByRole("row", { name: /Groceries/ })).toHaveTextContent("+20% (+100.00)");
    fireEvent.click(groceries);
    fireEvent.click(within(table).getByRole("button", { name: "Supermarket" }));
    const panel = await screen.findByRole("region", { name: "Lines: Groceries / Supermarket" });
    expect(await within(panel).findByText("SUPERMAXI SAMPLE STORE")).toBeInTheDocument();
    expect(within(panel).getByText("+10.00")).toBeInTheDocument(); // the refund
    expect(within(panel).getByText(/2 lines/)).toHaveTextContent("190.00");
    expect(urls).toContain("/api/spending/lines?month=2026-09-01&group_id=1&category_id=11");
    fireEvent.click(within(panel).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("region", { name: /Lines:/ })).toBeNull();
  });

  it("breaks the month down by person, country, fixed and merchant", async () => {
    renderAt("/spending?view=fixed");
    const person = await screen.findByRole("region", { name: "By person" });
    expect(person).toHaveTextContent("Shared");
    expect(person).toHaveTextContent("73%");
    fireEvent.click(within(person).getByRole("button", { name: /Hernan/ }));
    expect(await screen.findByRole("region", { name: "Lines: Hernan" })).toBeInTheDocument();
    expect(urls).toContain("/api/spending/lines?month=2026-09-01&person=Hernan");
    fireEvent.click(
      within(screen.getByRole("region", { name: "Fixed or variable" })).getByRole("button", {
        name: /Fixed/,
      }),
    );
    expect(await screen.findByRole("region", { name: "Lines: Fixed spending" })).toBeInTheDocument();
    expect(urls).toContain("/api/spending/lines?month=2026-09-01&fixed=true");
    fireEvent.click(
      within(screen.getByRole("region", { name: "By country" })).getByRole("button", { name: /Ecuador/ }),
    );
    expect(urls).toContain("/api/spending/lines?month=2026-09-01&country=EC");
    fireEvent.click(screen.getByRole("button", { name: "Merchants" }));
    const merchants = await screen.findByRole("region", { name: /^Merchants in/ });
    expect(await within(merchants).findByText("2 invoices")).toBeInTheDocument();
    expect(within(merchants).getByText("none")).toBeInTheDocument();
    expect(within(merchants).getByText("340.00")).toBeInTheDocument(); // the total
    fireEvent.click(within(merchants).getByRole("button", { name: "SUPERMAXI" }));
    expect(await screen.findByRole("region", { name: "Lines: SUPERMAXI" })).toBeInTheDocument();
  });

  it("shows groups as blocks that open their merchants, products and ways to save", async () => {
    renderAt("/spending?month=2026-09");
    const map = await screen.findByRole("group", { name: /Spending by group/ });
    fireEvent.click(within(map).getAllByRole("button")[0]);
    const path = await screen.findByRole("navigation", { name: "Drill path" });
    expect(within(path).getByText("All spending")).toBeInTheDocument();
    expect(urls.some((u) => u.startsWith("/api/spending/merchants?month=2026-09-01&group_id="))).toBe(true);
    fireEvent.click(within(path).getByRole("button", { name: "All spending" }));
    expect(screen.queryByRole("navigation", { name: "Drill path" })).not.toBeInTheDocument();

    const ideas = await screen.findByRole("region", { name: /Ways to save/ });
    expect(within(ideas).getByRole("link", { name: "Look →" })).toHaveAttribute(
      "href",
      "/spending?month=2026-09&view=merchants",
    );

    fireEvent.click(screen.getByRole("button", { name: "Products" }));
    const products = await screen.findByRole("region", { name: /by product, from the invoices/ });
    expect(await within(products).findByText("+16%")).toBeInTheDocument();
    expect(within(products).getByText("would have saved")).toHaveTextContent("would have saved 0.90");
    fireEvent.change(within(products).getByLabelText("Product group"), {
      target: { value: "Not grouped yet" },
    });
    expect(within(products).queryByText("Leche 1L")).not.toBeInTheDocument();
    expect(within(products).getByText("Pan")).toBeInTheDocument();
  });

  it("moves between months from the picker, the buttons and the chart", async () => {
    renderAt("/spending?month=2026-09");
    await screen.findByRole("table", { name: /Spending by category/ });
    fireEvent.click(screen.getByRole("button", { name: "← Earlier" }));
    fireEvent.click(await screen.findByRole("button", { name: "Later →" }));
    await screen.findByRole("table", { name: /Spending by category/ });
    fireEvent.change(screen.getByLabelText("Month"), { target: { value: "2026-08-01" } });
    await screen.findByRole("table", { name: /Spending by category/ });
    fireEvent.click(await screen.findByTestId("stack-2026-10-01"));
    expect(urls).toEqual(
      expect.arrayContaining(["/api/spending?month=2026-08-01", "/api/spending?month=2026-10-01"]),
    );
    expect(screen.getByText("The numbers")).toBeInTheDocument();
  });

  it("says when a month comes from the sheet, when nothing is loaded and on errors", async () => {
    body = { ...SPENDING, source: "excel", merchants: [] };
    const { unmount } = renderAt();
    expect(await screen.findByText("From the Cash Flow sheet: categories, no merchants")).toBeInTheDocument();
    unmount();
    body = { ...SPENDING, source: "none", months: [], groups: [] };
    const second = renderAt();
    expect(await screen.findByText(/No spending loaded yet/)).toBeInTheDocument();
    second.unmount();
    body = { detail: "boom" };
    vi.mocked(fetch).mockImplementation((url) =>
      Promise.resolve(
        String(url).startsWith("/api/me/settings")
          ? new Response(JSON.stringify({ user: "local", settings: {} }))
          : new Response(JSON.stringify({ detail: "boom" }), { status: 500 }),
      ),
    );
    renderAt();
    expect(await screen.findByText("Could not load spending: boom")).toBeInTheDocument();
  });

  it("follows the Both/Hernan/Lauren switch, with a way back to both", async () => {
    settings = { person: "Lauren" };
    renderAt("/spending?month=2026-09");
    expect(await screen.findByText("Showing Lauren’s lines only.")).toBeInTheDocument();
    expect(urls[0]).toBe("/api/spending?month=2026-09-01&person=Lauren");
    fireEvent.click(screen.getByRole("button", { name: "Show both" }));
    await waitFor(() => expect(urls).toContain("/api/spending?month=2026-09-01"));
    expect(screen.queryByText("Showing Lauren’s lines only.")).not.toBeInTheDocument();
  });
});
