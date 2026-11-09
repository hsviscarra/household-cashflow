import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Groceries } from "../api";
import GroceriesPage from "./Groceries";

const G: Groceries = {
  month: "2026-10-01",
  spent: "620.00",
  usual: "500.00",
  invoiced: "310.00",
  weeks: "4.43",
  trend: ["05", "06", "07", "08", "09", "10"].map((m) => ({
    month: `2026-${m}-01`,
    spent: "500.00",
    invoiced: "250.00",
  })),
  aisles: [
    { name: "Meat & Fish", amount: "120.00", lines: 6, usual: "100.00" },
    { name: "Not grouped yet", amount: "40.00", lines: 9, usual: "0.00" },
  ],
  products: [
    {
      product_key: "LECHE",
      description: "LECHE ENTERA 1L",
      product_group: "Dairy & Eggs",
      times: 4,
      quantity: "8",
      amount: "9.60",
      unit_price: "1.20",
      before: "1.05",
      change: "0.1429",
      stores: ["CORPORACION FAVORITA C.A."],
      cheaper_store: null,
      cheaper_price: null,
      could_save: "0",
    },
  ],
  stores: [{ name: "CORPORACION FAVORITA C.A.", invoices: 5, amount: "310.00" }],
  missing: [
    { transaction_id: 3, txn_date: "2026-10-18", merchant: "MEGAMAXI", amount: "150.00", account_name: "Capital One" },
  ],
  ungrouped_products: 9,
};

let urls: string[];
beforeEach(() => {
  urls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      urls.push(url);
      return Promise.resolve(new Response(JSON.stringify(G), { status: 200 }));
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("Groceries", () => {
  it("puts the month's spending next to what the invoices say it bought", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/groceries?month=2026-10"]}>
          <GroceriesPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("620.00")).toBeInTheDocument();
    expect(urls[0]).toContain("month=2026-10-01");
    expect(screen.getByText("+24% vs usual")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    const missing = screen.getByRole("region", { name: /Charges without their invoice/ });
    expect(within(missing).getByText(/MEGAMAXI/)).toBeInTheDocument();
    expect(screen.getByText(/9 products aren't in an aisle yet/)).toBeInTheDocument();
    expect(screen.getByText("+14%")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /October 2026: spent 500.00/ })).toHaveAttribute("href", expect.stringContaining("month=2026-10"));
  });
});
