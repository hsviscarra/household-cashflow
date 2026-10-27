import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
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
let body: unknown;

beforeEach(() => {
  urls = [];
  body = SPENDING;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      urls.push(url);
      const out = url.startsWith("/api/spending/lines") ? LINES : body;
      return Promise.resolve(new Response(JSON.stringify(out)));
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

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
    renderAt();
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
    const merchants = screen.getByRole("list", { name: "Top merchants" });
    fireEvent.click(within(merchants).getByRole("button", { name: /SUPERMAXI/ }));
    expect(await screen.findByRole("region", { name: "Lines: SUPERMAXI" })).toBeInTheDocument();
  });

  it("moves between months from the picker, the buttons and the chart", async () => {
    renderAt("/spending?month=2026-09");
    await screen.findByRole("table", { name: /Spending by category/ });
    fireEvent.click(screen.getByRole("button", { name: "← Earlier" }));
    fireEvent.click(await screen.findByRole("button", { name: "Later →" }));
    await screen.findByRole("table", { name: /Spending by category/ });
    fireEvent.change(screen.getByLabelText("Month"), { target: { value: "2026-08-01" } });
    await screen.findByRole("table", { name: /Spending by category/ });
    fireEvent.click(screen.getByTestId("bar-2026-10-01"));
    expect(urls).toEqual(
      expect.arrayContaining(["/api/spending?month=2026-08-01", "/api/spending?month=2026-10-01"]),
    );
    expect(screen.getByText("The numbers")).toBeInTheDocument();
  });

  it("says when a month comes from the sheet, when nothing is loaded and on errors", async () => {
    body = { ...SPENDING, source: "excel", merchants: [] };
    const { unmount } = renderAt();
    expect(await screen.findByText("From the Cash Flow sheet: categories, no merchants")).toBeInTheDocument();
    expect(
      screen.getByText("Months from the Cash Flow sheet have category rows, not merchants."),
    ).toBeInTheDocument();
    unmount();
    body = { ...SPENDING, source: "none", months: [], groups: [] };
    const second = renderAt();
    expect(await screen.findByText(/No spending loaded yet/)).toBeInTheDocument();
    second.unmount();
    vi.mocked(fetch).mockImplementationOnce(() =>
      Promise.resolve(new Response(JSON.stringify({ detail: "boom" }), { status: 500 })),
    );
    renderAt();
    expect(await screen.findByText("Could not load spending: boom")).toBeInTheDocument();
  });
});
