import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { BalanceSheet, LoanSchedule, SheetItem } from "../api";
import BalanceSheetSection, {
  freshness,
  maybeDuplicate,
  monthlyDebt,
  sheetHeadline,
  whatIf,
} from "./NetWorth";

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

function renderIt(mode: "overview" | "manage" = "manage") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <BalanceSheetSection mode={mode} />
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
      await screen.findByRole("heading", { level: 1, name: "Manage what you own and owe" }),
    ).toBeInTheDocument();
    const own = await screen.findByRole("region", { name: "What you own" });
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
    expect(screen.queryByRole("img", { name: /^Net worth by month/ })).not.toBeInTheDocument();
  });

  it("the overview reads: totals, each item on one line, the trend, and a way to manage", async () => {
    renderIt("overview");
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Net worth 84,500.00: you own 126,000.00 and owe 41,500.00",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Still to pay on purchases").nextSibling).toHaveTextContent("94,000.00");
    const own = screen.getByRole("region", { name: "What you own" });
    expect(within(own).getByRole("listitem", { name: "Home" })).toHaveTextContent("100,000.00");
    expect(within(own).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Paused (not counted)" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add something you own or owe" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Update a value, add an item/ })).toHaveAttribute(
      "href",
      "/debt/manage",
    );
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

describe("loan amortization table", () => {
  const schedule: LoanSchedule = {
    installments: 12,
    paid: 10,
    left: 2,
    next_period: "2026-11-01",
    next_total: "1022.5",
    payoff: "2026-12-01",
    balance: "2000",
    interest_this_year: "750",
    interest_left: "30",
    other_left: "5",
  };
  const withTable = (s: LoanSchedule | null): BalanceSheet => ({
    ...SHEET,
    items: SHEET.items.map((i) => (i.name === "Mortgage" ? { ...i, loan: { ...i.loan!, schedule: s } } : i)),
  });
  const payments = [
    {
      number: 9,
      period: "2026-09-01",
      total: "1042.5",
      status: "paid",
      line_id: 1,
      line_date: "2026-09-05",
      line_amount: "-1042",
      line_description: "PAGO IESS",
      account_name: "Pichincha Ahorros",
    },
    {
      number: 10,
      period: "2026-10-01",
      total: "1032.5",
      status: "paid",
      line_id: null,
      line_date: null,
      line_amount: null,
      line_description: null,
      account_name: null,
    },
    {
      number: 11,
      period: "2026-11-01",
      total: "1022.5",
      status: "due",
      line_id: null,
      line_date: null,
      line_amount: null,
      line_description: null,
      account_name: null,
    },
  ];
  function stub(sheet: BalanceSheet, upload: () => Response) {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        const json = (v: unknown, status = 200) =>
          Promise.resolve(new Response(JSON.stringify(v), { status }));
        if (url === "/api/networth") return json(sheet);
        if (url === "/api/holdings/3/payments") return json(payments);
        if (url === "/api/holdings/3/schedule" && init?.method === "POST") {
          expect(init.body).toBeInstanceOf(FormData);
          return Promise.resolve(upload());
        }
        return json([]);
      }),
    );
  }

  it("uploads a table and reports what it read", async () => {
    stub(
      withTable(null),
      () =>
        new Response(
          JSON.stringify({ installments: 12, paid: 10, due: 2, balance: "2000", as_of: "2026-10-01" }),
        ),
    );
    renderIt();
    const card = await screen.findByRole("listitem", { name: "Mortgage" });
    expect(within(card).getByText(/Paying/)).toHaveTextContent("Paying 505.19 a month");
    expect(within(card).getByText("Upload amortization table (PDF)")).toBeInTheDocument();
    const file = new File(["%PDF"], "tabla.pdf", { type: "application/pdf" });
    fireEvent.change(within(card).getByLabelText("Amortization table for Mortgage"), {
      target: { files: [file] },
    });
    expect(
      await screen.findByText("Read 12 installments: 10 paid, 2 to go; balance 2,000.00."),
    ).toBeInTheDocument();
  });

  it("reports a table that doesn't check out", async () => {
    stub(
      withTable(null),
      () =>
        new Response(JSON.stringify({ detail: "The table doesn't check out: Installment 3 is missing." }), {
          status: 422,
        }),
    );
    renderIt();
    const card = await screen.findByRole("listitem", { name: "Mortgage" });
    fireEvent.change(within(card).getByLabelText("Amortization table for Mortgage"), {
      target: { files: [new File(["x"], "t.pdf")] },
    });
    expect(
      await screen.findByText(
        "Could not read the table: The table doesn't check out: Installment 3 is missing.",
      ),
    ).toBeInTheDocument();
  });

  it("summarizes the schedule and checks payments against the bank", async () => {
    stub(withTable(schedule), () => new Response("{}"));
    renderIt();
    const card = await screen.findByRole("listitem", { name: "Mortgage" });
    expect(within(card).getByText(/installments paid/)).toHaveTextContent(
      "10 of 12 installments paid · next 1,022.50 in November 2026 · paid off December 2026",
    );
    expect(within(card).getByText(/Interest this year/)).toHaveTextContent(
      "Interest this year 750.00 · still to pay 30.00 interest and 5.00 insurance and charges over 2 months",
    );
    expect(within(card).queryByText(/payments this year/)).toBeNull();
    // What if (ADR-032): 100 more a month doesn't shorten 2 payments; 2,000 more does.
    expect(within(card).getByText(/still ends with the last payment/)).toBeInTheDocument();
    fireEvent.change(within(card).getByLabelText("Extra a month on Mortgage"), { target: { value: "2000" } });
    expect(card).toHaveTextContent("ends it 1 month sooner (1 payments instead of 2)");
    expect(within(card).getByText("Upload a newer amortization table")).toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "Payments" }));
    const list = await within(card).findByRole("list", { name: "Payments for Mortgage" });
    expect(within(card).getByText(/of 2 paid installments found/)).toHaveTextContent("1 of 2");
    const rows = within(list).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent(
      "#9 · September 2026 · 1,042.50Paid Sep 5, 2026 from Pichincha Ahorros (1,042.00)",
    );
    expect(rows[1]).toHaveTextContent("Lender says paid; no bank line found");
    expect(rows[2]).toHaveTextContent("Due");
  });

  it("a paid-off loan and a failed payments load", async () => {
    stub(
      withTable({ ...schedule, paid: 12, left: 0, next_period: null, next_total: null }),
      () => new Response("{}"),
    );
    vi.mocked(fetch).mockImplementation((url) =>
      Promise.resolve(
        String(url).endsWith("/payments")
          ? new Response(JSON.stringify({ detail: "boom" }), { status: 500 })
          : new Response(
              JSON.stringify(
                withTable({ ...schedule, paid: 12, left: 0, next_period: null, next_total: null }),
              ),
            ),
      ),
    );
    renderIt();
    const card = await screen.findByRole("listitem", { name: "Mortgage" });
    expect(within(card).getByText(/installments paid/)).toHaveTextContent(
      "12 of 12 installments paid · paid off",
    );
    expect(within(card).getByText(/Interest this year/)).toHaveTextContent("over 0 months");
    fireEvent.click(within(card).getByRole("button", { name: "Payments" }));
    expect(await within(card).findByText("Could not load the payments: boom")).toBeInTheDocument();
  });
});

describe("ADR-032: freshness, duplicates, debt a month and what if", () => {
  const ON = "2026-11-06";
  it("says when a value is out of date, by kind", () => {
    expect(freshness(item({ holding_class: "cash", as_of: "2026-10-01" }), ON)).toEqual({
      stale: false,
      age: 36,
    });
    expect(freshness(item({ holding_class: "cash", as_of: "2026-08-31" }), ON).stale).toBe(true);
    expect(freshness(item({ holding_class: "investment", as_of: "2026-10-20" }), ON).stale).toBe(true);
    expect(freshness(item({ holding_class: "property", as_of: "2026-01-10" }), ON).stale).toBe(false);
    expect(freshness(item({ holding_class: "personal_loan", as_of: "2020-01-01" }), ON).stale).toBe(false);
    expect(freshness(item({ holding_class: "card", as_of: null }), ON)).toEqual({ stale: true, age: null });
  });

  it("flags an old workbook value next to a fresh one of the same kind", () => {
    const old = item({
      key: "x",
      name: "Produbanco (workbook)",
      holding_class: "cash",
      source: "excel",
      as_of: "2026-04-30",
    });
    const bank = item({
      key: "y",
      name: "Produbanco Hernan",
      holding_class: "cash",
      source: "statement",
      as_of: "2026-10-31",
    });
    expect(maybeDuplicate(old, [old, bank], ON)).toBe("Produbanco Hernan");
    expect(maybeDuplicate(bank, [old, bank], ON)).toBeNull();
    expect(maybeDuplicate(old, [old], ON)).toBeNull();
  });

  it("adds loan payments and installments a month", () => {
    const loan = item({ loan: { monthly_payment: "505.19", paid_this_year: "0", payments_this_year: 0 } });
    const buy = item({
      purchase: {
        target: "1",
        paid: "0",
        remaining: "1",
        installment: "3075.36",
        installments_left: 16,
        full_price: null,
        at_delivery: null,
        lines: "0",
      },
    });
    expect(monthlyDebt([loan, buy, { ...loan, is_active: false }])).toBeCloseTo(3580.55);
  });

  it("works out how much sooner a loan ends with more each month", () => {
    // 37,521 left over 129 months with 20,342 of interest: about 450 a month.
    const s = { balance: "37521.37", interest_left: "20342", left: 129 };
    const r = whatIf(s, 100)!;
    expect(r.months).toBeLessThan(129);
    expect(r.sooner).toBe(129 - r.months);
    expect(r.saved).toBeGreaterThan(0);
    expect(whatIf(s, 0)).toBeNull();
    expect(whatIf({ ...s, balance: null }, 100)).toBeNull();
  });

  it("shows only what's out of date, with a way back", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify(SHEET)))),
    );
    renderIt();
    const button = await screen.findByRole("button", { name: /^Update values \(\d+ out of date\)$/ });
    fireEvent.click(button);
    expect(screen.getByText(/Showing the \d+ values? out of date/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show everything" }));
    expect(screen.queryByText(/Showing the \d+ values? out of date/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Update values/ })).toBeInTheDocument();
  });

  it("the overview sends you to manage for what's out of date", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify(SHEET)))),
    );
    renderIt("overview");
    expect(await screen.findByRole("link", { name: /^Update values \(\d+ out of date\)$/ })).toHaveAttribute(
      "href",
      "/debt/manage?stale=1",
    );
    expect(screen.getByText("Debt payments a month")).toBeInTheDocument();
  });
});
