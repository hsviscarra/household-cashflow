import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Review, Txn } from "../api";
import ReviewPage, { confidenceLabel } from "./Review";
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

beforeEach(() => {
  calls = [];
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
  ];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url.startsWith("/api/review/suggest"))
        return json({ asked: 1, suggested: 1, model: "claude-haiku-5-5" });
      if (url === "/api/review/resolve") {
        review = { ...review, groups: review.groups.slice(1), uncategorized_lines: 2 };
        return json({ categorized: 1, rule_id: 77, also_by_rule: 2 });
      }
      if (url.startsWith("/api/review")) return json(review);
      if (url === "/api/categories") return json(CATEGORIES);
      if (url.startsWith("/api/transactions?")) return json(txns);
      if (url.endsWith("/history")) return json([]);
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

describe("Review", () => {
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
    expect(within(rent).getByLabelText(/^Category for/)).toHaveValue("1");
    fireEvent.click(within(rent).getByRole("button", { name: "Categorize 1 line" }));
    expect(
      await screen.findByText(/Rule saved for next time; it also categorized 2 more\./),
    ).toBeInTheDocument();
    const sent = calls.find((c) => c.url === "/api/review/resolve")?.body as Record<string, unknown>;
    expect(sent).toMatchObject({ category_id: 1, save_rule: true, from_suggestion: true });
    expect(await screen.findByText("2 lines from 1 merchant need a category.")).toBeInTheDocument();
  });

  it("sets a rule's pattern and amount range", async () => {
    renderAt("/review?month=2026-07");
    const visa = await screen.findByRole("listitem", { name: "DEBITO VISA" });
    fireEvent.change(within(visa).getByLabelText(/^Category for/), { target: { value: "3" } });
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
    fireEvent.click(await screen.findByRole("button", { name: "Ask Claude about 1 merchants" }));
    expect(await screen.findByText(/Claude suggested a category for 1 of 1 merchants/)).toBeInTheDocument();
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
    fireEvent.change(await within(table).findByLabelText("Category"), { target: { value: "3" } });
    fireEvent.click(within(table).getByRole("button", { name: "Save" }));
    expect(await within(table).findByText("Saved: Groceries / Supermarket.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ category_id: 3 });
  });

  it("splits a line only when the parts add up", async () => {
    renderAt("/transactions?month=2026-07");
    const table = await screen.findByRole("table", { name: "Transactions in July 2026" });
    fireEvent.click(within(table).getByRole("button", { name: /Edit PAGO TARJETA/ }));
    fireEvent.click(await within(table).findByRole("button", { name: "Split across categories" }));
    const form = within(table).getByRole("form", { name: "Split PAGO TARJETA" });
    const save = within(form).getByRole("button", { name: "Save split" });
    fireEvent.change(within(form).getByLabelText("Part 1"), { target: { value: "70" } });
    expect(within(form).getByText("30.00 left to assign")).toBeInTheDocument();
    expect(save).toBeDisabled();
    fireEvent.change(within(form).getByLabelText("Part 2"), { target: { value: "30" } });
    fireEvent.change(within(form).getByLabelText("Category of part 2"), { target: { value: "1" } });
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
