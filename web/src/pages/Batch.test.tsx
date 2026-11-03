import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Batch, Statement } from "../api";
import BatchPage from "./Batch";
import { pickCategory } from "../test/pick";
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

const XYZ_LINE = {
  transaction_id: 3,
  txn_date: "2026-09-02",
  amount: "-40.00",
  description: "NEW MERCHANT XYZ",
  account_name: "Capital One Venture",
  person: "Lauren",
};
const CATEGORIES = [
  {
    category_id: 6,
    parent_id: null,
    name: "Shopping",
    kind: "expense",
    color: "#C2185B",
    is_fixed: false,
    is_active: true,
    sort_order: 0,
    children: [
      {
        category_id: 7,
        parent_id: 6,
        name: "Other Retail",
        kind: "expense",
        color: null,
        is_fixed: false,
        is_active: true,
        sort_order: 0,
        description: "Other stores: electronics, home goods.",
      },
    ],
  },
];
let current: Batch;
let calls: string[];
let suggestion: {
  category_id: number;
  category_path: string;
  confidence: string;
  reason: string;
  model: string;
} | null;
let available: boolean;
const batchReview = () => ({
  month: null,
  groups:
    current.uncategorized > 0
      ? [{ merchant_key: "NEW MERCHANT XYZ", lines: [XYZ_LINE], total: "-40.00", suggestion }]
      : [],
  uncategorized_lines: current.uncategorized,
  suggestions_available: available,
});
const categorizeXyz = () => {
  current = {
    ...current,
    uncategorized: 0,
    lines: current.lines.map((l) =>
      l.category_id ? l : { ...l, category_id: 7, category_path: "Shopping / Other Retail" },
    ),
  };
};
beforeEach(() => {
  current = batch();
  calls = [];
  suggestion = null;
  available = true;
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
      if (url === "/api/batches/9/review") return json(batchReview());
      if (url === "/api/categories") return json(CATEGORIES);
      if (url === "/api/batches/9/resolve") {
        categorizeXyz();
        return json({ categorized: 1, rule_id: 31, also_by_rule: 0, waiting_by_rule: 2 });
      }
      if (url === "/api/batches/9/suggest") {
        suggestion = {
          category_id: 7,
          category_path: "Shopping / Other Retail",
          confidence: "0.9",
          reason: "a store",
          model: "claude-haiku-5-5",
        };
        return json({ asked: 1, suggested: 1, model: "claude-haiku-5-5" });
      }
      if (url === "/api/batches/9/accept-suggestions") {
        categorizeXyz();
        return json({ merchants: 1, lines: 1, also_by_rule: 0 });
      }
      if (url === "/api/batches/9/apply-rules") {
        const done = current.uncategorized;
        current = {
          ...current,
          uncategorized: 0,
          lines: current.lines.map((l) =>
            l.category_id ? l : { ...l, category_id: 7, category_path: "Shopping / Other Retail" },
          ),
        };
        return json({ categorized: done, batch: current });
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

  it("applies rules saved after the statement was read", async () => {
    renderAt("/import/batches/9");
    fireEvent.click(await screen.findByRole("button", { name: "Apply rules again" }));
    expect(await screen.findByText("Rules categorized 1 more line.")).toBeInTheDocument();
    expect(calls).toContain("POST /api/batches/9/apply-rules");
    const lines = screen.getByRole("table", { name: "Statement lines" });
    expect(within(lines).getByText("Shopping / Other Retail")).toBeInTheDocument();
    // Nothing left to categorize: the button goes away.
    expect(screen.queryByRole("button", { name: "Apply rules again" })).not.toBeInTheDocument();
  });

  it("says when no rule matches", async () => {
    current = batch();
    const fetchMock = vi.mocked(fetch);
    const real = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation((url, init) =>
      url === "/api/batches/9/apply-rules"
        ? Promise.resolve(new Response(JSON.stringify({ categorized: 0, batch: current })))
        : real(url, init),
    );
    renderAt("/import/batches/9");
    fireEvent.click(await screen.findByRole("button", { name: "Apply rules again" }));
    expect(
      await screen.findByText("No rule matches the lines that still need a category."),
    ).toBeInTheDocument();
  });

  it("categorizes a merchant on the statement page before approving", async () => {
    renderAt("/import/batches/9");
    const section = await screen.findByRole("region", { name: "Needs a category" });
    expect(section).toHaveTextContent("1 line from 1 merchant");
    const card = within(section).getByRole("listitem", { name: "NEW MERCHANT XYZ" });
    pickCategory(
      within(card).getByRole("combobox", { name: "Category for NEW MERCHANT XYZ" }),
      "retail",
      "Shopping / Other Retail",
    );
    fireEvent.click(within(card).getByRole("button", { name: "Categorize 1 line" }));
    expect(
      await within(section).findByText(
        "NEW MERCHANT XYZ: 1 line → Shopping / Other Retail. Rule saved for next time and 2 in statements waiting for approval.",
      ),
    ).toBeInTheDocument();
    expect(calls).toContain("POST /api/batches/9/resolve");
    // Every line has a category now: the section goes and the header says so.
    await waitFor(() => expect(screen.queryByRole("region", { name: "Needs a category" })).toBeNull());
    expect(screen.queryByText(/need a category/)).toBeNull();
  });

  it("asks Claude about this statement, then accepts the likely suggestion", async () => {
    renderAt("/import/batches/9");
    const section = await screen.findByRole("region", { name: "Needs a category" });
    fireEvent.click(within(section).getByRole("button", { name: "Ask Claude about 1 merchants" }));
    expect(
      await within(section).findByText(/Claude suggested a category for 1 of 1 merchants/),
    ).toBeInTheDocument();
    expect(calls).toContain("POST /api/batches/9/suggest");
    expect(await within(section).findByText(/Claude suggests/)).toHaveTextContent("(likely, 90%): a store");
    fireEvent.click(within(section).getByRole("button", { name: "✓ Accept 1 likely suggestion" }));
    await waitFor(() => expect(calls).toContain("POST /api/batches/9/accept-suggestions"));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Needs a category" })).toBeNull());
  });

  it("uses one suggestion with a click; says when Claude is off", async () => {
    suggestion = {
      category_id: 7,
      category_path: "Shopping / Other Retail",
      confidence: "0.6",
      reason: "maybe a store",
      model: "claude-haiku-5-5",
    };
    available = false;
    renderAt("/import/batches/9");
    const section = await screen.findByRole("region", { name: "Needs a category" });
    expect(section).toHaveTextContent("Claude suggestions are off");
    // 60% is not "likely": no accept-all, but the one-click button is there.
    expect(within(section).queryByRole("button", { name: /likely suggestion/ })).toBeNull();
    fireEvent.click(
      within(section).getByRole("button", { name: "Use Shopping / Other Retail for NEW MERCHANT XYZ" }),
    );
    await waitFor(() => expect(calls).toContain("POST /api/batches/9/resolve"));
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
    expect(screen.queryByText(/covered by the Excel history/)).toBeNull();
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
        line(3, "TIENDA DIFERIDO", "-50.00", {
          account_name: "BofA Adv Plus Banking",
          pay_reference: "2/6",
        }),
      ],
    });
    renderAt("/import/batches/9");
    const table = await screen.findByRole("table", { name: "Statement lines" });
    expect(within(table).getByRole("columnheader", { name: "Account" })).toBeInTheDocument();
    expect(within(table).getByText("BofA Regular Savings")).toBeInTheDocument();
    expect(within(table).getByText(/payer’s label: “August”/)).toBeInTheDocument();
    expect(within(table).getByText(/installment 2 of 6/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "BofA Adv Plus Banking, BofA Regular Savings",
    );
  });
});
