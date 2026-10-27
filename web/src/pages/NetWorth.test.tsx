import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { BalanceSheet, SheetItem } from "../api";
import BalanceSheetSection, { sheetHeadline } from "./NetWorth";

const item = (over: Partial<SheetItem>): SheetItem => ({
  key: "holding-1",
  name: "Home",
  side: "asset",
  holding_class: "property",
  value: "100000",
  as_of: "2025-01-01",
  source: "manual",
  holding_id: 1,
  account_id: null,
  is_active: true,
  notes: null,
  history: [{ snapshot_id: 11, as_of: "2025-01-01", amount: "100000", source: "manual", notes: "bought" }],
  purchase: null,
  loan: null,
  category_id: null,
  recurring_template_id: null,
  ...over,
});
const SHEET: BalanceSheet = {
  as_of: "2026-10-27",
  assets: "126000",
  liabilities: "41500",
  net_worth: "84500",
  commitments: "94000",
  items: [
    item({}),
    item({
      key: "holding-2",
      name: "Flat",
      holding_class: "purchase",
      value: "6000",
      holding_id: 2,
      history: [],
      purchase: {
        target: "30000",
        paid: "6000",
        remaining: "24000",
        installment: "1000",
        installments_left: 24,
        full_price: "100000",
        at_delivery: "70000",
        lines: "1000",
      },
    }),
    item({
      key: "account-5",
      name: "Savings",
      holding_class: "cash",
      value: "20000",
      source: "statement",
      holding_id: null,
      account_id: 5,
      history: [],
    }),
    item({
      key: "holding-3",
      name: "Mortgage",
      side: "liability",
      holding_class: "loan",
      value: "40000",
      source: "excel",
      holding_id: 3,
      history: [{ snapshot_id: 30, as_of: "2026-01-31", amount: "40000", source: "excel", notes: null }],
      loan: { monthly_payment: "505.19", paid_this_year: "1010.38", payments_this_year: 2 },
    }),
    item({
      key: "account-6",
      name: "Card",
      side: "liability",
      holding_class: "card",
      value: "1500",
      source: "statement",
      holding_id: null,
      account_id: 6,
      history: [],
    }),
    item({
      key: "holding-4",
      name: "Old card",
      side: "liability",
      holding_class: "card",
      value: "0",
      holding_id: 4,
      is_active: false,
    }),
  ],
  series: [
    { month: "2026-09-01", assets: "120000", liabilities: "42000", net: "78000" },
    { month: "2026-10-01", assets: "126000", liabilities: "41500", net: "84500" },
  ],
};
let calls: { method: string; url: string; body?: unknown }[];

beforeEach(() => {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const json = (v: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(v), { status }));
      if (url === "/api/networth") return json(SHEET);
      if (url === "/api/categories")
        return json([
          {
            category_id: 9,
            parent_id: null,
            name: "Savings & Debt",
            kind: "savings",
            color: null,
            is_fixed: false,
            is_active: true,
            sort_order: 0,
            children: [],
          },
        ]);
      if (url === "/api/recurring/templates") return json([{ template_id: 7, name: "BIESS Depo" }]);
      if (url === "/api/holdings" && method === "POST") return json({ holding_id: 9 }, 201);
      if (url.startsWith("/api/holdings/values/"))
        return Promise.resolve(new Response(null, { status: 204 }));
      if (url.endsWith("/values"))
        return json({
          snapshot_id: 12,
          as_of: "2026-10-01",
          amount: "105000",
          source: "manual",
          notes: null,
        });
      if (method === "PATCH") return json({ holding_id: 1 });
      if (method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
      return json({ detail: "not found" }, 404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <BalanceSheetSection />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("balance sheet", () => {
  it("states net worth and lists what is owned and owed by kind", async () => {
    expect(sheetHeadline({ ...SHEET, items: [] })).toBe("Debt & Net Worth");
    expect(sheetHeadline({ ...SHEET, net_worth: "-5" })).toBe(
      "Net worth −5.00: you own 126,000.00 and owe 41,500.00",
    );
    renderIt();
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Net worth 84,500.00: you own 126,000.00 and owe 41,500.00",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Still to pay on purchases").nextSibling).toHaveTextContent("94,000.00");
    const own = screen.getByRole("region", { name: "What you own" });
    expect(within(own).getByText(/Property ·/)).toHaveTextContent("100,000.00");
    const flat = within(own).getByRole("listitem", { name: "Flat" });
    expect(flat).toHaveTextContent("Paid 6,000.00 of 30,000.00 · 24,000.00 to go (24 × 1,000.00)");
    expect(flat).toHaveTextContent("at delivery 70,000.00 to finance");
    expect(within(flat).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "20");
    expect(within(own).getByRole("listitem", { name: "Savings" })).toHaveTextContent(
      "Updates with each approved statement.",
    );
    const owe = screen.getByRole("region", { name: "What you owe" });
    expect(within(owe).getByRole("listitem", { name: "Mortgage" })).toHaveTextContent(
      "Paying 505.19 a month · 2 payments this year (1,010.38)",
    );
    expect(screen.getByRole("region", { name: "Paused (not counted)" })).toHaveTextContent("Old card");
    expect(screen.getByRole("img", { name: /^Net worth by month/ })).toBeInTheDocument();
  });

  it("updates a value, shows and edits its history", async () => {
    renderIt();
    const home = await screen.findByRole("listitem", { name: "Home" });
    fireEvent.click(within(home).getByRole("button", { name: "Update value" }));
    const form = within(home).getByRole("form", { name: "New value for Home" });
    fireEvent.change(within(form).getByLabelText("Value"), { target: { value: "105000" } });
    fireEvent.change(within(form).getByLabelText("On"), { target: { value: "2026-10-01" } });
    fireEvent.change(within(form).getByLabelText("Note (optional)"), { target: { value: "appraisal" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save value" }));
    expect(await screen.findByText("Home: 105,000.00 on Oct 1, 2026.")).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/holdings/1/values")?.body).toEqual({
      as_of: "2026-10-01",
      amount: "105000",
      notes: "appraisal",
    });
    fireEvent.click(within(home).getByRole("button", { name: "History (1)" }));
    const history = within(home).getByRole("list", { name: "History of Home" });
    expect(history).toHaveTextContent("bought");
    fireEvent.click(within(history).getByRole("button", { name: "Remove the value of Jan 1, 2025" }));
    expect(await screen.findByText("Value removed.")).toBeInTheDocument();
    // A workbook value can't be removed here.
    const mortgage = screen.getByRole("listitem", { name: "Mortgage" });
    fireEvent.click(within(mortgage).getByRole("button", { name: "History (1)" }));
    expect(within(mortgage).queryByRole("button", { name: /Remove the value/ })).toBeNull();
  });

  it("adds a purchase and a loan, edits, pauses and removes", async () => {
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Add something you own or owe" }));
    const form = screen.getByRole("form", { name: "Add something you own or owe" });
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: " New flat " } });
    fireEvent.change(within(form).getByLabelText("What it is"), { target: { value: "purchase" } });
    fireEvent.change(within(form).getByLabelText("Paid so far"), { target: { value: "5000" } });
    fireEvent.change(within(form).getByLabelText("Value on"), { target: { value: "2026-08-01" } });
    fireEvent.change(within(form).getByLabelText("Down payment to pay"), { target: { value: "30000" } });
    fireEvent.change(within(form).getByLabelText("Each installment"), { target: { value: "1000" } });
    fireEvent.change(within(form).getByLabelText("Full price"), { target: { value: "100000" } });
    await within(form).findByRole("option", { name: "Savings & Debt" });
    fireEvent.change(within(form).getByLabelText("Payments’ category (optional)"), {
      target: { value: "9" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Add" }));
    expect(await screen.findByText("New flat added.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST" && c.url === "/api/holdings")?.body).toEqual({
      name: "New flat",
      holding_class: "purchase",
      side: null,
      target_amount: "30000",
      installment: "1000",
      full_price: "100000",
      category_id: 9,
      recurring_template_id: null,
      notes: null,
      value: "5000",
      as_of: "2026-08-01",
    });

    const mortgage = screen.getByRole("listitem", { name: "Mortgage" });
    fireEvent.click(within(mortgage).getByRole("button", { name: "Edit" }));
    const edit = within(mortgage).getByRole("form", { name: "Edit Mortgage" });
    await within(edit).findByRole("option", { name: "BIESS Depo" });
    fireEvent.change(within(edit).getByLabelText(/Monthly payment/), { target: { value: "7" } });
    fireEvent.click(within(edit).getByRole("button", { name: "Save" }));
    await screen.findByText("Mortgage saved.");
    expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ recurring_template_id: 7 });

    const home = screen.getByRole("listitem", { name: "Home" });
    fireEvent.click(within(home).getByRole("button", { name: "Edit" }));
    fireEvent.click(within(home).getByRole("button", { name: "Pause (don’t count it)" }));
    expect(await screen.findByText("Home paused: not counted.")).toBeInTheDocument();
    fireEvent.click(within(home).getByRole("button", { name: "Edit" }));
    fireEvent.click(within(home).getByRole("button", { name: "Remove…" }));
    fireEvent.click(within(home).getByRole("button", { name: "Remove Home and its values" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "DELETE" && c.url === "/api/holdings/1")).toBe(true),
    );

    // "Other" asks whether it is owned or owed.
    fireEvent.click(screen.getByRole("button", { name: "Add something you own or owe" }));
    const other = screen.getByRole("form", { name: "Add something you own or owe" });
    fireEvent.change(within(other).getByLabelText("What it is"), { target: { value: "other" } });
    expect(within(other).getByLabelText("You")).toHaveValue("asset");
  });

  it("reports errors", async () => {
    vi.mocked(fetch).mockImplementationOnce(() =>
      Promise.resolve(new Response(JSON.stringify({ detail: "boom" }), { status: 500 })),
    );
    renderIt();
    expect(await screen.findByText("Could not load the balance sheet: boom")).toBeInTheDocument();
  });
});
