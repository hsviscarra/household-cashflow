import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Batch, Statement } from "../api";
import BatchPage from "./Batch";
import { StatementsCard } from "./ImportStatements";
import TransactionsPage from "./Transactions";

const STATEMENT: Statement = {
  statement_file_id: 5,
  file_name: "co.pdf",
  source: "capitalone",
  source_label: "Capital One",
  status: "detected",
  accounts: [{ account_id: 3, name: "Capital One Venture", last4: "4003" }],
  account_match: "last4",
  last4_found: ["4003"],
  period_start: "2026-09-04",
  period_end: "2026-10-03",
  page_count: 4,
  size_bytes: 10,
  uploaded_by: "hernan@example.com",
  uploaded_at: "2026-10-20T15:00:00",
  can_read: true,
  batch: null,
};

const line = (id: number, desc: string, amount: string, extra: object = {}) => ({
  stg_id: id,
  txn_date: "2026-09-02",
  post_date: "2026-09-04",
  description: desc,
  merchant: null,
  amount,
  type: "expense",
  category_id: 1,
  category_path: "Dining / Food Delivery",
  person: "Lauren",
  country: "US",
  cardholder: "4003",
  is_duplicate: false,
  ...extra,
});

function batch(over: Partial<Batch> = {}): Batch {
  return {
    batch_id: 9,
    status: "preview",
    tieout_ok: true,
    statement: { ...STATEMENT, batch: { batch_id: 9, status: "preview", tieout_ok: true } },
    period_start: "2026-09-04",
    period_end: "2026-10-03",
    opening_balance: "1000",
    closing_balance: "806.75",
    checks: [
      { name: "Card #4003 transactions", expected: "100.00", actual: "100.00", ok: true },
      { name: "Interest", expected: "10.00", actual: "10.00", ok: true },
    ],
    lines: [
      line(1, "UBER EATS SAN JOSE", "-12.50"),
      line(2, "CAPITAL ONE MOBILE PYMT", "500.00", {
        type: "transfer",
        category_path: "Transfers / Card Payment",
      }),
      line(3, "NEW MERCHANT XYZ", "-40.00", { category_id: null, category_path: null }),
      line(4, "OLD LINE", "-5.00", { is_duplicate: true }),
    ],
    by_category: [
      { category_path: "Needs a category", type: "expense", lines: 1, amount: "-40.00" },
      { category_path: "Dining / Food Delivery", type: "expense", lines: 1, amount: "-12.50" },
    ],
    rejects: [],
    new_lines: 3,
    duplicate_lines: 1,
    uncategorized: 1,
    created_by: "hernan@example.com",
    decided_by: null,
    decided_at: null,
    ...over,
  };
}

let current: Batch;
let calls: string[];
beforeEach(() => {
  current = batch();
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push(`${method} ${url}`);
      const json = (d: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(d), { status }));
      if (url === "/api/batches/9" && method === "GET") return json(current);
      if (url === "/api/batches/9/approve") {
        current = {
          ...current,
          status: "approved",
          decided_by: "hernan@example.com",
          decided_at: "2026-10-20T16:00:00",
        };
        return json({ batch_id: 9, loaded: 3, skipped_duplicates: 1 });
      }
      if (url === "/api/batches/9/reject") {
        current = {
          ...current,
          status: "rejected",
          decided_by: "hernan@example.com",
          decided_at: "2026-10-20T16:00:00",
        };
        return json(current);
      }
      if (url === "/api/statements" && method === "GET") return json([STATEMENT]);
      if (url === "/api/statements/5/read") return json(batch());
      if (url.startsWith("/api/transactions"))
        return json(
          url.includes("2026-09")
            ? [
                {
                  transaction_id: 1,
                  txn_date: "2026-09-02",
                  post_date: null,
                  cash_month: "2026-09-01",
                  account_id: 3,
                  account_name: "Capital One Venture",
                  description: "UBER EATS SAN JOSE",
                  merchant: "UBER EATS",
                  amount: "-12.50",
                  type: "expense",
                  category_id: 1,
                  category_path: "Dining / Food Delivery",
                  person: "Lauren",
                  country: "US",
                  source: "statement",
                  statement_file_id: 5,
                },
                {
                  transaction_id: 2,
                  txn_date: "2026-09-27",
                  post_date: null,
                  cash_month: "2026-09-01",
                  account_id: 3,
                  account_name: "Capital One Venture",
                  description: "CAPITAL ONE MOBILE PYMT",
                  merchant: null,
                  amount: "500.00",
                  type: "transfer",
                  category_id: 2,
                  category_path: null,
                  person: "Lauren",
                  country: "US",
                  source: "statement",
                  statement_file_id: 5,
                },
              ]
            : [],
        );
      return json({ detail: "not found" }, 404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/import" element={<StatementsCard />} />
          <Route path="/import/batches/:batchId" element={<BatchPage />} />
          <Route path="/transactions" element={<TransactionsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Import batch", () => {
  it("reads a statement from the list and opens its preview", async () => {
    renderAt("/import");
    fireEvent.click(await screen.findByRole("button", { name: "Read lines of co.pdf" }));
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "Capital One Venture, Sep 4, 2026 – Oct 3, 2026",
    );
    expect(calls).toContain("POST /api/statements/5/read");
  });

  it("shows the tie-out, categories and lines, then approves", async () => {
    renderAt("/import/batches/9");
    expect(await screen.findByText("Ties out to the statement")).toBeInTheDocument();
    expect(screen.getByText(/3 new lines · 1 already loaded · 1 need a category/)).toBeInTheDocument();
    const lines = screen.getByRole("table", { name: "Statement lines" });
    expect(within(lines).getByText("+500.00")).toBeInTheDocument();
    expect(within(lines).getByText("12.50")).toBeInTheDocument();
    expect(within(lines).getByText("Already loaded")).toBeInTheDocument();
    expect(screen.getAllByText("Needs a category").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Approve import" }));
    expect(await screen.findByText("Import approved.")).toBeInTheDocument();
    expect(screen.getByText(/3 lines loaded, 1 skipped/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See the transactions" })).toHaveAttribute(
      "href",
      "/transactions?month=2026-10",
    );
    expect(await screen.findByText(/Loaded by hernan@example.com/)).toBeInTheDocument();
  });

  it("blocks approval when the statement does not tie out and can be discarded", async () => {
    current = batch({
      tieout_ok: false,
      checks: [{ name: "Transactions, all cards", expected: "105.00", actual: "100.00", ok: false }],
      rejects: [
        {
          page: 2,
          line_no: 9,
          text: "Sep 9 Sep 9 ODD LINE $1.00",
          reason: "Transaction outside a known section",
        },
      ],
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderAt("/import/batches/9");
    expect(await screen.findByText("Does not tie out")).toBeInTheDocument();
    expect(screen.getByText(/difference 5.00/)).toBeInTheDocument();
    expect(screen.getByText(/ODD LINE/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve import" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(await screen.findByText(/Discarded by hernan@example.com/)).toBeInTheDocument();
  });

  it("explains a missing batch", async () => {
    renderAt("/import/batches/77");
    expect(await screen.findByText(/Could not open this import/)).toBeInTheDocument();
  });
});

describe("Transactions", () => {
  it("lists a month's lines and changes month", async () => {
    renderAt("/transactions?month=2026-09");
    const table = await screen.findByRole("table", { name: "Transactions in September 2026" });
    expect(within(table).getByText("UBER EATS SAN JOSE")).toBeInTheDocument();
    expect(screen.getByText(/2 lines/)).toHaveTextContent("12.50 out");
    expect(within(table).getByText("+500.00")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Transactions (list)" })).toHaveTextContent(
      "Capital One Venture",
    );
    fireEvent.change(screen.getByLabelText("Month"), { target: { value: "2026-08" } });
    expect(await screen.findByText(/Nothing loaded for August 2026 yet/)).toBeInTheDocument();
  });
});

describe("Combined statements", () => {
  it("shows each line's account and the payer's label", async () => {
    current = batch({
      statement: {
        ...STATEMENT,
        source: "bofa",
        source_label: "Bank of America",
        accounts: [
          { account_id: 1, name: "BofA Adv Plus Banking", last4: "8872" },
          { account_id: 2, name: "BofA Regular Savings", last4: "1862" },
        ],
      },
      lines: [
        line(1, "Transfer Kenility LLC", "4000.00", {
          type: "income",
          category_path: "Salary / Hernan",
          account_name: "BofA Adv Plus Banking",
          pay_reference: "August",
          person: "Joint",
          cardholder: null,
        }),
        line(2, "Monthly Maintenance Fee", "-5.00", {
          account_name: "BofA Regular Savings",
          person: "Joint",
          cardholder: null,
        }),
      ],
    });
    renderAt("/import/batches/9");
    const table = await screen.findByRole("table", { name: "Statement lines" });
    expect(within(table).getByRole("columnheader", { name: "Account" })).toBeInTheDocument();
    expect(within(table).getByText("BofA Regular Savings")).toBeInTheDocument();
    expect(within(table).getByText(/payer’s label: “August”/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "BofA Adv Plus Banking, BofA Regular Savings",
    );
  });
});
