import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AutoState, Review, Txn } from "../api";
import ReviewPage, { confidenceLabel } from "./Review";
import { pickCategory } from "../test/pick";
import TransactionsPage from "./Transactions";

const CATEGORIES = [
  {
    category_id: 1,
    parent_id: null,
    name: "Office Rent",
    kind: "income",
    color: null,
    is_fixed: true,
    is_active: true,
    sort_order: 0,
    children: [],
  },
  {
    category_id: 2,
    parent_id: null,
    name: "Groceries",
    kind: "expense",
    color: null,
    is_fixed: false,
    is_active: true,
    sort_order: 1,
    children: [
      {
        category_id: 3,
        parent_id: 2,
        name: "Supermarket",
        kind: "expense",
        color: null,
        is_fixed: false,
        is_active: true,
        sort_order: 0,
      },
    ],
  },
];

let review: Review;
let calls: { method: string; url: string; body?: unknown }[];
const json = (v: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(v), { status }));

const txn = (over: Partial<Txn>): Txn => ({
  transaction_id: 1,
  txn_date: "2026-07-08",
  post_date: null,
  cash_month: "2026-07-01",
  account_id: 5,
  account_name: "Produbanco Ahorros Hernan",
  description: "TRANSFERENCIA CTAS TERCEROS BCA ENL",
  merchant: null,
  amount: "570.00",
  type: "income",
  category_id: null,
  category_path: null,
  person: "Hernan",
  country: "EC",
  source: "statement",
  statement_file_id: 9,
  notes: null,
  category_source: null,
  parent_transaction_id: null,
  parts: 0,
  ...over,
});
let txns: Txn[];
let unmatched: Txn[];
let auto: AutoState;
let who: Txn[];
const PEOPLE = [
  {
    counterparty_id: 7,
    name: "Rubén",
    patterns: null,
    category_id: null,
    category_path: null,
    holding_id: null,
    notes: null,
    is_active: true,
    lines: 0,
    paid: "0",
    received: "0",
    balance: null,
  },
];

beforeEach(() => {
  calls = [];
  auto = {
    threshold: "0.90",
    on: true,
    rules: [
      {
        rule_id: 41,
        pattern: "NETFLIX",
        category_id: 2,
        category_path: "Subscriptions",
        lines: 2,
        accepted_at: "2026-11-05T10:00:00",
        is_active: true,
      },
    ],
  };
  review = {
    month: null,
    uncategorized_lines: 3,
    suggestions_available: true,
    groups: [
      {
        merchant_key: "TRANSFERENCIA CTAS TERCEROS BCA ENL",
        total: "570.00",
        lines: [
          {
            transaction_id: 1,
            txn_date: "2026-07-08",
            amount: "570.00",
            description: "TRANSFERENCIA CTAS TERCEROS BCA ENL",
            account_name: "Produbanco Ahorros Hernan",
            person: "Hernan",
            post_date: "2026-07-09",
            statement_file_id: 9,
            page: 2,
          },
        ],
        suggestion: {
          category_id: 1,
          category_path: "Office Rent",
          confidence: "0.850",
          reason: "monthly incoming transfer",
          model: "claude-haiku-5-5",
        },
      },
      {
        merchant_key: "DEBITO VISA",
        total: "-52.24",
        lines: [
          {
            transaction_id: 2,
            txn_date: "2026-07-03",
            amount: "-40.24",
            description: "DEBITO VISA",
            account_name: "Produbanco Ahorros Hernan",
            person: null,
          },
          {
            transaction_id: 3,
            txn_date: "2026-07-15",
            amount: "-12.00",
            description: "DEBITO VISA",
            account_name: "Produbanco Ahorros Hernan",
            person: null,
          },
        ],
        suggestion: null,
      },
    ],
  };
  txns = [
    txn({
      transaction_id: 10,
      description: "PAGO TARJETA",
      amount: "-100.00",
      type: "expense",
      category_id: 3,
      category_path: "Groceries / Supermarket",
      category_source: "rule",
    }),
    txn({ transaction_id: 11, amount: "-40.24", description: "DEBITO VISA", type: "expense" }),
    txn({
      transaction_id: 12,
      txn_date: "2026-07-20",
      description: "PAGO TARJETA CREDITO",
      amount: "-150.00",
      type: "transfer",
      category_id: 3,
      category_path: "Transfers / Card Payment",
      category_source: "match",
      transfer_group_id: 12,
      transfer_with: {
        transaction_id: 40,
        txn_date: "2026-07-21",
        amount: "150.00",
        description: "SU PAGO",
        account_id: 7,
        account_name: "Diners Club",
        account_kind: "credit_card",
      },
    }),
  ];
  who = [
    txn({
      transaction_id: 30,
      txn_date: "2026-07-20",
      description: "TRANSFERENCIA DIRECTA 0099",
      amount: "-250.00",
      type: "transfer",
    }),
  ];
  unmatched = [
    txn({
      transaction_id: 20,
      txn_date: "2026-07-25",
      description: "PAGO TARJETA OTRO BANCO",
      amount: "-300.00",
      type: "transfer",
    }),
  ];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url.startsWith("/api/transfers/unmatched")) return json(unmatched);
      if (url === "/api/transfers/match" && method === "POST") {
        unmatched = [];
        return json({ pairs: 1 });
      }
      if (url === "/api/transfers/12" && method === "DELETE") {
        txns = txns.map((t) =>
          t.transaction_id === 12 ? { ...t, transfer_group_id: null, transfer_with: null } : t,
        );
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.startsWith("/api/review/accept-suggestions")) {
        review = { ...review, groups: review.groups.slice(1), uncategorized_lines: 2 };
        return json({ merchants: 1, lines: 1, also_by_rule: 4 });
      }
      if (url.startsWith("/api/review/suggest"))
        return json({ asked: 1, suggested: 1, model: "claude-haiku-5-5" });
      if (url === "/api/review/auto") return json(auto);
      if (url.startsWith("/api/review/auto/") && method === "POST") {
        auto = { ...auto, rules: [] };
        return json({ lines: 2 });
      }
      if (url.startsWith("/api/review/who") && method === "GET") return json(who);
      if (url === "/api/review/who" && method === "POST") {
        who = [];
        return json(txns[0]);
      }
      if (url === "/api/people") return json(PEOPLE);
      if (url === "/api/review/resolve-many") {
        review = { ...review, groups: [], uncategorized_lines: 0 };
        return json({ merchants: 2, lines: 3, also_by_rule: 0, skipped: 1 });
      }
      if (url === "/api/review/resolve") {
        review = { ...review, groups: review.groups.slice(1), uncategorized_lines: 2 };
        return json({ categorized: 1, rule_id: 77, also_by_rule: 2, waiting_by_rule: 3 });
      }
      if (url.startsWith("/api/review")) return json(review);
      if (url === "/api/categories") return json(CATEGORIES);
      if (url.startsWith("/api/transactions?")) return json(txns);
      if (url.endsWith("/history")) return json([]);
      if (url === "/api/transactions/1/source")
        return json({
          transaction_id: 1,
          txn_date: "2026-07-08",
          post_date: "2026-07-09",
          amount: "570.00",
          description: "TRANSFERENCIA CTAS TERCEROS BCA ENL",
          account_name: "Produbanco Ahorros Hernan",
          account_last4: "4321",
          person: "Hernan",
          pay_reference: "AGOSTO",
          notes: null,
          statement_file_id: 9,
          file_name: "jul.pdf",
          bank: "produbanco",
          period_start: "2026-07-01",
          period_end: "2026-07-31",
          page: 2,
          line_no: 14,
          section: "credit",
          cardholder: null,
          text: "08 Jul TRANSFERENCIA CTAS TERCEROS BCA ENL 570.00",
          around: [
            { line_no: 13, text: "07 Jul DEBITO VISA 12.00", is_line: false },
            { line_no: 14, text: "08 Jul TRANSFERENCIA CTAS TERCEROS BCA ENL 570.00", is_line: true },
            { line_no: 15, text: "DE: MARIA PEREZ CTA ••••5678", is_line: false },
          ],
          note_from: "MARIA PEREZ",
          note_person: null,
          note: "Arriendo julio",
          similar: [
            {
              txn_date: "2026-06-08",
              amount: "570.00",
              description: "TRANSFERENCIA CTAS TERCEROS BCA ENL",
              category_id: 1,
              category_path: "Office Rent",
            },
          ],
          unreadable: false,
        });
      if (url === "/api/transactions/11" && method === "PATCH") {
        txns = txns.map((t) =>
          t.transaction_id === 11
            ? { ...t, category_id: 3, category_path: "Groceries / Supermarket", category_source: "manual" }
            : t,
        );
        return json(txns[1]);
      }
      if (url === "/api/transactions/10/split" && method === "PUT") {
        txns = [{ ...txns[0], parts: 2 }, txns[1]];
        return json([]);
      }
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
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/transactions" element={<TransactionsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Review: one click for Claude's suggestions", () => {
  it("uses a suggestion with one click, keeping the rule", async () => {
    renderAt("/review?month=2026-07");
    fireEvent.click(
      await screen.findByRole("button", { name: "Use Office Rent for TRANSFERENCIA CTAS TERCEROS BCA ENL" }),
    );
    expect(
      await screen.findByText(/TRANSFERENCIA CTAS TERCEROS BCA ENL: 1 line → Office Rent\. Rule saved/),
    ).toBeInTheDocument();
    const sent = calls.find((c) => c.url === "/api/review/resolve")?.body as Record<string, unknown>;
    expect(sent).toMatchObject({ category_id: 1, save_rule: true, from_suggestion: true });
  });

  it("accepts every likely suggestion at once", async () => {
    renderAt("/review?month=2026-07");
    fireEvent.click(await screen.findByRole("button", { name: "✓ Accept 1 likely suggestion" }));
    expect(
      await screen.findByText(
        "Accepted 1 suggestion: 1 line categorized and a rule saved for each; the rules also categorized 4 more.",
      ),
    ).toBeInTheDocument();
    expect(calls.map((c) => `${c.method} ${c.url}`)).toContain(
      "POST /api/review/accept-suggestions?month=2026-07-01",
    );
    expect(
      await screen.findByText("2 lines from 1 merchant need a category in July 2026."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /likely suggestion/ })).not.toBeInTheDocument();
  });
});

describe("Review: one merchant, two categories", () => {
  it("categorizes only the ticked lines, without a rule", async () => {
    renderAt("/review?month=2026-07");
    const visa = await screen.findByRole("listitem", { name: "DEBITO VISA" });
    expect(visa).toHaveTextContent("Untick the ones that don't go with this one.");
    expect(within(visa).getByLabelText("Use for this merchant from now on (save a rule)")).toBeChecked();
    fireEvent.click(within(visa).getByRole("checkbox", { name: "Include Jul 15, 12.00" }));
    expect(visa).toHaveTextContent("1 of 2 chosen.");
    // A rule would catch both lines: it turns off.
    expect(within(visa).getByLabelText("Use for this merchant from now on (save a rule)")).not.toBeChecked();
    pickCategory(
      within(visa).getByRole("combobox", { name: /^Category for/ }),
      "super",
      "Groceries / Supermarket",
    );
    fireEvent.click(within(visa).getByRole("button", { name: "Categorize 1 of 2 lines" }));
    await waitFor(() => expect(calls.some((c) => c.url === "/api/review/resolve")).toBe(true));
    const sent = calls.find((c) => c.url === "/api/review/resolve")?.body as Record<string, unknown>;
    expect(sent).toMatchObject({ transaction_ids: [2], save_rule: false, pattern: null });
  });

  it("can't save with no line ticked; ticking all goes back to the whole merchant", async () => {
    renderAt("/review?month=2026-07");
    const visa = await screen.findByRole("listitem", { name: "DEBITO VISA" });
    fireEvent.click(within(visa).getByRole("checkbox", { name: "Include Jul 3, 40.24" }));
    fireEvent.click(within(visa).getByRole("checkbox", { name: "Include Jul 15, 12.00" }));
    pickCategory(
      within(visa).getByRole("combobox", { name: /^Category for/ }),
      "super",
      "Groceries / Supermarket",
    );
    expect(within(visa).getByRole("button", { name: "Categorize 0 of 2 lines" })).toBeDisabled();
    fireEvent.click(within(visa).getByRole("checkbox", { name: "Include Jul 3, 40.24" }));
    fireEvent.click(within(visa).getByRole("checkbox", { name: "Include Jul 15, 12.00" }));
    expect(within(visa).getByRole("button", { name: "Categorize 2 lines" })).toBeEnabled();
  });
});

describe("Review", () => {
  it("shows the full date, a link to the statement page and what the statement says", async () => {
    renderAt("/review?month=2026-07");
    expect(await screen.findByText("Wed, Jul 8, 2026")).toBeInTheDocument();
    expect(screen.getByText(/posted Jul 9/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the statement, page 2" })).toHaveAttribute(
      "href",
      "/api/statements/9/file#page=2",
    );
    expect(screen.getByText(/the next statements categorize this merchant on their own/)).toBeInTheDocument();
    const more = screen.getAllByRole("button", { name: "More details" })[0];
    fireEvent.click(more);
    const box = await screen.findByLabelText("Details of Wed, Jul 8, 2026");
    expect(box).toHaveTextContent("Produbanco Ahorros Hernan ····4321");
    expect(box).toHaveTextContent("ReferenceAGOSTO");
    expect(box).toHaveTextContent("Kind on the statementMoney in");
    expect(box).toHaveTextContent("jul.pdf (Jul 1 to Fri, Jul 31, 2026)");
    expect(box).toHaveTextContent("page 2, line 14");
    expect(box).toHaveTextContent("From the transfer email: MARIA PEREZ · “Arriendo julio”");
    expect(within(box).getByText("08 Jul TRANSFERENCIA CTAS TERCEROS BCA ENL 570.00")).toHaveClass(
      "font-bold",
    );
    expect(within(box).getByText("DE: MARIA PEREZ CTA ••••5678")).toBeInTheDocument();
    expect(within(box).getByRole("list", { name: "The same merchant before" })).toHaveTextContent(
      "Mon, Jun 8, 2026 · +570.00 → Office Rent",
    );
    expect(more).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(more);
    expect(screen.queryByLabelText("Details of Wed, Jul 8, 2026")).toBeNull();
  });

  it("labels confidence with a word and a number", () => {
    expect(confidenceLabel("0.850")).toBe("likely, 85%");
    expect(confidenceLabel("0.6")).toBe("maybe, 60%");
    expect(confidenceLabel("0.2")).toBe("unsure, 20%");
  });

  it("resolves a merchant with Claude's suggestion and saves a rule", async () => {
    renderAt("/review");
    expect(await screen.findByText("3 lines from 2 merchants need a category.")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Merchants to review" });
    const rent = within(list).getByRole("listitem", { name: "TRANSFERENCIA CTAS TERCEROS BCA ENL" });
    expect(rent).toHaveTextContent("Claude suggests Office Rent (likely, 85%)");
    // The suggestion is preselected; saving keeps the rule checkbox on.
    expect(within(rent).getByRole("combobox", { name: /^Category for/ })).toHaveValue("Office Rent");
    fireEvent.click(within(rent).getByRole("button", { name: "Categorize 1 line" }));
    expect(
      await screen.findByText(
        /Rule saved for next time; it also categorized 2 more and 3 in statements waiting for approval\./,
      ),
    ).toBeInTheDocument();
    const sent = calls.find((c) => c.url === "/api/review/resolve")?.body as Record<string, unknown>;
    expect(sent).toMatchObject({ category_id: 1, save_rule: true, from_suggestion: true });
    expect(await screen.findByText("2 lines from 1 merchant need a category.")).toBeInTheDocument();
  });

  it("sets a rule's pattern and amount range", async () => {
    renderAt("/review?month=2026-07");
    const visa = await screen.findByRole("listitem", { name: "DEBITO VISA" });
    pickCategory(
      within(visa).getByRole("combobox", { name: /^Category for/ }),
      "super",
      "Groceries / Supermarket",
    );
    fireEvent.click(within(visa).getByRole("button", { name: "Rule details" }));
    fireEvent.change(within(visa).getByLabelText("Up to"), { target: { value: "50" } });
    fireEvent.change(within(visa).getByLabelText("Match"), { target: { value: "starts_with" } });
    fireEvent.click(within(visa).getByRole("button", { name: "Categorize 2 lines" }));
    await screen.findByText(/DEBITO VISA: 1 line → Groceries \/ Supermarket/);
    const sent = calls.find((c) => c.url === "/api/review/resolve")?.body as Record<string, unknown>;
    expect(sent).toMatchObject({
      amount_max: "50",
      amount_min: null,
      match_type: "starts_with",
      from_suggestion: false,
    });
    expect(calls.some((c) => c.url === "/api/review?month=2026-07-01")).toBe(true);
  });

  it("asks Claude about merchants without a suggestion", async () => {
    renderAt("/review");
    fireEvent.click(await screen.findByRole("button", { name: "Ask Claude about 1 merchant" }));
    expect(await screen.findByText(/Claude suggested a category for 1 of 1 merchants/)).toBeInTheDocument();
  });

  it("lists transfers without their other side and matches again", async () => {
    renderAt("/review?month=2026-07");
    const list = await screen.findByRole("list", { name: "Unmatched transfers" });
    expect(within(list).getByText("PAGO TARJETA OTRO BANCO")).toBeInTheDocument();
    expect(calls.some((c) => c.url === "/api/transfers/unmatched?month=2026-07-01")).toBe(true);
    expect(screen.getByRole("link", { name: "Upload a statement" })).toHaveAttribute("href", "/import");
    fireEvent.click(screen.getByRole("button", { name: "Match transfers again" }));
    expect(await screen.findByText("Matched 1 transfer with their other side.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("list", { name: "Unmatched transfers" })).toBeNull());
  });

  it("says when suggestions are off and when nothing is left", async () => {
    review = { ...review, suggestions_available: false };
    const { unmount } = renderAt("/review");
    expect(await screen.findByText(/Claude suggestions are off/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Ask Claude/ })).toBeNull();
    unmount();
    review = { ...review, groups: [], uncategorized_lines: 0 };
    renderAt("/review?month=2026-07");
    expect(await screen.findByText("Every line has a category in July 2026.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See the transactions" })).toHaveAttribute(
      "href",
      "/transactions?month=2026-07",
    );
  });
});

describe("Transactions editing", () => {
  it("edits a category with undo, and points to Review", async () => {
    renderAt("/transactions?month=2026-07");
    expect(await screen.findByText(/1 line needs a category/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review them" })).toHaveAttribute(
      "href",
      "/review?month=2026-07",
    );
    const table = screen.getByRole("table", { name: "Transactions in July 2026" });
    expect(within(table).getByText("· by rule")).toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: /Edit DEBITO VISA/ }));
    pickCategory(
      await within(table).findByRole("combobox", { name: "Category" }),
      "super",
      "Groceries / Supermarket",
    );
    fireEvent.click(within(table).getByRole("button", { name: "Save" }));
    expect(await within(table).findByText("Saved: Groceries / Supermarket.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ category_id: 3 });
  });

  it("shows a matched transfer's other side and unlinks it", async () => {
    renderAt("/transactions?month=2026-07");
    const table = await screen.findByRole("table", { name: "Transactions in July 2026" });
    expect(within(table).getByText(/↔ Diners Club/)).toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: /Edit PAGO TARJETA CREDITO/ }));
    expect(await within(table).findByText(/Matched transfer: the other side is/)).toBeInTheDocument();
    expect(within(table).queryByRole("button", { name: "Split across categories" })).toBeNull();
    fireEvent.click(within(table).getByRole("button", { name: "Not the same money: unlink" }));
    await waitFor(() => expect(within(table).queryByText(/↔ Diners Club/)).toBeNull());
    expect(calls.some((c) => c.method === "DELETE" && c.url === "/api/transfers/12")).toBe(true);
  });

  it("splits a line only when the parts add up", async () => {
    renderAt("/transactions?month=2026-07");
    const table = await screen.findByRole("table", { name: "Transactions in July 2026" });
    fireEvent.click(within(table).getByRole("button", { name: /Edit PAGO TARJETA on/ }));
    fireEvent.click(await within(table).findByRole("button", { name: "Split across categories" }));
    const form = within(table).getByRole("form", { name: "Split PAGO TARJETA" });
    const save = within(form).getByRole("button", { name: "Save split" });
    fireEvent.change(within(form).getByLabelText("Part 1"), { target: { value: "70" } });
    expect(within(form).getByText("30.00 left to assign")).toBeInTheDocument();
    expect(save).toBeDisabled();
    fireEvent.change(within(form).getByLabelText("Part 2"), { target: { value: "30" } });
    pickCategory(within(form).getByRole("combobox", { name: "Category of part 2" }), "rent", "Office Rent");
    expect(within(form).getByText("Fully assigned")).toBeInTheDocument();
    fireEvent.click(save);
    expect(await within(table).findByText("Split into 2")).toBeInTheDocument();
    const body = calls.find((c) => c.method === "PUT")?.body as {
      parts: { amount: string; category_id: number }[];
    };
    expect(body.parts).toEqual([
      { amount: "-70.00", category_id: 3 },
      { amount: "-30.00", category_id: 1 },
    ]);
  });
});

describe("Inbox: autopilot, many at once, keys and who", () => {
  it("shows autopilot's rules and undoes one", async () => {
    renderAt("/review");
    expect(
      await screen.findByRole("heading", { name: /Autopilot is on: Claude’s suggestions at 90% or more/ }),
    ).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Accepted on their own" });
    expect(list).toHaveTextContent("NETFLIX → Subscriptions · 2 lines · Nov 5");
    fireEvent.click(within(list).getByRole("button", { name: "Undo NETFLIX → Subscriptions" }));
    expect(await screen.findByText("Rule turned off; 2 lines are back in the Inbox.")).toBeInTheDocument();
    expect(calls.some((c) => c.url === "/api/review/auto/41/undo" && c.method === "POST")).toBe(true);
  });

  it("says when autopilot is off", async () => {
    auto = { threshold: "0.90", on: false, rules: [] };
    renderAt("/review");
    expect(await screen.findByText(/Autopilot is off/)).toBeInTheDocument();
  });

  it("categorizes several merchants together, or accepts their suggestions", async () => {
    renderAt("/review");
    const bar = await screen.findByRole("region", { name: "Selected merchants" });
    fireEvent.click(within(bar).getByLabelText("Select all"));
    expect(within(bar).getByText("2 selected")).toBeInTheDocument();
    fireEvent.click(within(bar).getByRole("button", { name: "✓ Accept 1 suggestion" }));
    expect(
      await screen.findByText(/2 merchants done: 3 lines categorized and a rule saved for each\. 1 skipped/),
    ).toBeInTheDocument();
    const sent = calls.find((c) => c.url === "/api/review/resolve-many")?.body as Record<string, unknown>;
    expect(sent).toMatchObject({ category_id: null, save_rule: true });
    expect((sent.merchant_keys as string[]).length).toBe(2);
  });

  it("picks one category for the selected merchants", async () => {
    renderAt("/review");
    const visa = await screen.findByRole("listitem", { name: "DEBITO VISA" });
    fireEvent.click(within(visa).getByLabelText("Select DEBITO VISA"));
    const bar = screen.getByRole("region", { name: "Selected merchants" });
    pickCategory(
      within(bar).getByRole("combobox", { name: "Category for the selected merchants" }),
      "super",
      "Groceries / Supermarket",
    );
    fireEvent.click(within(bar).getByRole("button", { name: "Categorize 1" }));
    await waitFor(() => expect(calls.some((c) => c.url === "/api/review/resolve-many")).toBe(true));
    const sent = calls.find((c) => c.url === "/api/review/resolve-many")?.body as Record<string, unknown>;
    expect(sent).toMatchObject({ merchant_keys: ["DEBITO VISA"], category_id: 3 });
  });

  it("moves with j and k, accepts with a, selects with x", async () => {
    renderAt("/review");
    const list = await screen.findByRole("list", { name: "Merchants to review" });
    const [first, second] = within(list)
      .getAllByRole("listitem")
      .filter((li) => li.parentElement === list);
    fireEvent.keyDown(window, { key: "j" });
    expect(first).toHaveFocus();
    fireEvent.keyDown(window, { key: "j" });
    expect(second).toHaveFocus();
    fireEvent.keyDown(window, { key: "k" });
    expect(first).toHaveFocus();
    fireEvent.keyDown(window, { key: "x" });
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "?" });
    expect(screen.getByText(/accept the suggestion/)).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "a" });
    await waitFor(() => expect(calls.some((c) => c.url === "/api/review/resolve")).toBe(true));
    fireEvent.keyDown(window, { key: "c" });
    // Typing in a field is left alone.
    const box = within(list).getAllByRole("combobox")[0];
    box.focus();
    fireEvent.keyDown(box, { key: "j" });
    expect(box).toHaveFocus();
  });

  it("asks who a transfer was for", async () => {
    renderAt("/review");
    const who = await screen.findByRole("list", { name: "Transfers without a person" });
    const pick = await within(who).findByLabelText(/Who was Jul 20/);
    await waitFor(() => expect(within(pick).getByRole("option", { name: "Rubén" })).toBeInTheDocument());
    fireEvent.change(pick, { target: { value: "7" } });
    expect(await screen.findByText("Marked as Rubén’s.")).toBeInTheDocument();
    const sent = calls.find((c) => c.url === "/api/review/who" && c.method === "POST")?.body;
    expect(sent).toEqual({ transaction_id: 30, counterparty_id: 7 });
  });
});
