import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Groceries, GroceryTrends } from "../api";
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
    {
      transaction_id: 3,
      txn_date: "2026-10-18",
      merchant: "MEGAMAXI",
      amount: "150.00",
      account_name: "Capital One",
    },
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
    expect(screen.getByTestId("stack-2026-10")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("link", { name: /A year by aisle/ })).toHaveAttribute(
      "href",
      expect.stringContaining("view=trends"),
    );
  });

  it("shows a year by aisle, compares two months and lists the patterns", async () => {
    const T: GroceryTrends = {
      month: "2026-10-01",
      months: [
        {
          month: "2026-09-01",
          spent: "400.00",
          invoiced: "100.00",
          trips: 2,
          basket: "50.00",
          aisles: { "Dairy & Eggs": "60.00", Pantry: "40.00" },
        },
        {
          month: "2026-10-01",
          spent: "450.00",
          invoiced: "130.00",
          trips: 3,
          basket: "43.33",
          aisles: { "Dairy & Eggs": "100.00", Pantry: "30.00" },
        },
      ],
      aisles: ["Dairy & Eggs", "Pantry"],
      cells: [
        {
          month: "2026-09-01",
          aisle: "Dairy & Eggs",
          type: "Milk",
          brand: "Vita",
          amount: "60.00",
          lines: 3,
        },
        { month: "2026-09-01", aisle: "Pantry", type: "Rice", brand: null, amount: "40.00", lines: 2 },
        {
          month: "2026-10-01",
          aisle: "Dairy & Eggs",
          type: "Milk",
          brand: "Vita",
          amount: "100.00",
          lines: 5,
        },
        { month: "2026-10-01", aisle: "Pantry", type: "Rice", brand: null, amount: "30.00", lines: 2 },
      ],
      weekdays: [0, 1, 2, 3, 4, 5, 6].map((day) => ({
        day,
        trips: day === 5 ? 4 : 0,
        amount: day === 5 ? "230.00" : "0",
      })),
      risers: [
        {
          product_key: "LECHE",
          description: "LECHE 1L",
          aisle: "Dairy & Eggs",
          first_month: "2026-09-01",
          first_price: "1.00",
          last_month: "2026-10-01",
          last_price: "1.25",
          change: "0.25",
          amount: "40",
        },
      ],
      fallers: [],
      new: [
        {
          product_key: "QUESO",
          description: "QUESO FRESCO",
          aisle: "Dairy & Eggs",
          months: 0,
          usual: "7.00",
        },
      ],
      skipped: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        urls.push(url);
        return Promise.resolve(new Response(JSON.stringify(T), { status: 200 }));
      }),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/groceries?month=2026-10&view=trends"]}>
          <GroceriesPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Month by month, by aisle")).toBeInTheDocument();
    expect(urls.at(-1)).toContain("/groceries/trends");
    expect(urls.at(-1)).toContain("months=12");
    const compare = screen.getByRole("region", { name: "Compare two months" });
    const dairy = within(compare).getByText("Dairy & Eggs").closest("tr")!;
    expect(within(dairy).getByText("+40.00")).toBeInTheDocument();
    expect(within(dairy).getByText("+67%")).toBeInTheDocument();
    fireEvent.click(within(compare).getByRole("radio", { name: "Brand" }));
    expect(within(compare).getByText("No brand yet")).toBeInTheDocument();
    expect(screen.getAllByText("Saturday").length).toBeGreaterThan(0);
    expect(screen.getByText("+25%")).toBeInTheDocument();
    expect(screen.getByText("QUESO FRESCO")).toBeInTheDocument();
  });
});
