import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CategoryGroup, Todo } from "../api";
import { pickCategory } from "../test/pick";
import TodoPage from "./Todo";

const CAT = { kind: "expense", color: null, is_fixed: false, is_active: true, sort_order: 0 } as const;
const GROUPS: CategoryGroup[] = [
  {
    ...CAT,
    kind: "income",
    category_id: 1,
    parent_id: null,
    name: "Income",
    children: [{ ...CAT, kind: "income", category_id: 2, parent_id: 1, name: "Salary" }],
  },
];

const TODO: Todo = {
  today: "2026-11-08",
  total: 7,
  sections: [
    {
      key: "categorize",
      title: "Needs a category",
      hint: "",
      count: 3,
      tasks: [
        {
          key: "cat:NETFLIX",
          kind: "categorize",
          title: "NETFLIX",
          detail: "3 lines · last Oct 14",
          amount: "-46.47",
          on: "2026-10-14",
          link: "/review",
          data: { merchant_key: "NETFLIX", transaction_ids: [1, 2, 3], suggested_category_id: null, statement_file_id: 9, page: 2 },
        },
      ],
    },
    {
      key: "who",
      title: "Who or what is it",
      hint: "",
      count: 1,
      tasks: [
        {
          key: "who:7",
          kind: "who",
          title: "TRANSFERENCIA KENILITY",
          detail: "Oct 30 · Produbanco",
          amount: "4200.00",
          on: "2026-10-30",
          link: "/transactions",
          data: { transaction_id: 7, merchant_key: "TRANSFERENCIA KENILITY" },
        },
      ],
    },
    {
      key: "values",
      title: "Out-of-date values",
      hint: "",
      count: 1,
      tasks: [
        {
          key: "value:h-3",
          kind: "duplicate",
          title: "Stock Market",
          detail: "Probably the same money as Interactive Brokers · 192 days old",
          amount: "13500.00",
          on: "2026-04-30",
          link: "/networth",
          data: { holding_id: 3 },
        },
      ],
    },
    {
      key: "books",
      title: "Statements, imports and bills",
      hint: "",
      count: 2,
      tasks: [
        {
          key: "statement:x",
          kind: "statement",
          title: "Produbanco Visa statement not uploaded",
          detail: "October 2026",
          amount: null,
          on: null,
          link: "/import",
          data: {},
        },
      ],
    },
  ],
};

let calls: { method: string; url: string; body: unknown }[];
let todo: Todo;

beforeEach(() => {
  calls = [];
  todo = structuredClone(TODO);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      calls.push({ method, url, body });
      const json = (d: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(d), { status }));
      if (url === "/api/todo") return json(todo);
      if (url === "/api/categories") return json(GROUPS);
      if (url === "/api/people" && method === "POST") return json({ counterparty_id: 9, name: "Napoles" }, 201);
      if (url === "/api/people") return json([{ counterparty_id: 4, name: "Rubén", is_active: true }]);
      if (url === "/api/review/resolve") return json({ categorized: 3, rule_id: 11, also_by_rule: 0 });
      if (url === "/api/transactions/7") return json({ transaction_id: 7 });
      if (url === "/api/merchant-rules") return json({ rule_id: 12, pattern: "X", category_path: "Income / Salary" }, 201);
      if (url === "/api/review/who") return json({ transaction_id: 7 });
      if (url === "/api/holdings/3") return json({ holding_id: 3 });
      if (url === "/api/holdings/3/values") return json({ snapshot_id: 1 });
      if (url === "/api/people" && method === "POST") return json({ counterparty_id: 9, name: "Napoles" }, 201);
      if (url === "/api/todo/dismiss" || url === "/api/transfers/8/one-sided")
        return Promise.resolve(new Response(null, { status: 204 }));
      if (url === "/api/holdings/5/installments/41/paid")
        return json({ number: 41, period: "2026-11-01", balance_after: "98000.00" });
      return json({ detail: "not here" }, 404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function cleanupAndRender() {
  cleanup();
  renderPage();
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TodoPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function open(name: RegExp | string) {
  const nav = screen.getByRole("navigation", { name: "Sections" });
  fireEvent.click(within(nav).getByRole("button", { name }));
  return screen.getByRole("region", { name: typeof name === "string" ? name : undefined });
}

describe("To do", () => {
  it("shows one section at a time, with what to do and a way to act", async () => {
    renderPage();
    const nav = await screen.findByRole("navigation", { name: "Sections" });
    expect(within(nav).getByRole("button", { name: /Needs a category/ })).toHaveAttribute("aria-current", "true");
    expect(screen.getByText(/Pick a category for each merchant/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Out-of-date values" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "statement" })).toHaveAttribute("href", expect.stringContaining("9"));
    fireEvent.click(within(nav).getByRole("button", { name: /Statements, imports and bills/ }));
    const books = screen.getByRole("region", { name: "Statements, imports and bills" });
    expect(within(books).getByRole("link", { name: "Upload it" })).toHaveAttribute("href", "/import");
    expect(within(books).getByText("And 1 more: they show here as you finish these.")).toBeInTheDocument();
  });

  it("categorizes a merchant, saves the rule and takes it off the list", async () => {
    renderPage();
    const box = await screen.findByRole("region", { name: "Needs a category" });
    pickCategory(await within(box).findByRole("combobox", { name: /Category for NETFLIX/ }), "Sal", "Salary");
    expect(await screen.findByText("Categorized 3 lines, saved a rule.")).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/review/resolve")!.body).toEqual({
      merchant_key: "NETFLIX",
      category_id: 2,
      transaction_ids: [1, 2, 3],
      save_rule: true,
    });
    expect(within(box).queryByText("NETFLIX")).not.toBeInTheDocument();
  });

  it("calls a transfer income, or gives it a new person", async () => {
    renderPage();
    await screen.findByRole("navigation", { name: "Sections" });
    let box = open(/Who or what is it/);
    pickCategory(
      await within(box).findByRole("combobox", { name: /Category for TRANSFERENCIA KENILITY/ }),
      "Sal",
      "Salary",
    );
    expect(await screen.findByText("Categorized, and saved a rule for next time.")).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/transactions/7")!.body).toEqual({ category_id: 2 });
    expect(calls.find((c) => c.url === "/api/merchant-rules")!.body).toMatchObject({
      pattern: "TRANSFERENCIA KENILITY",
      category_id: 2,
    });

    todo = structuredClone(TODO);
    cleanupAndRender();
    await screen.findByRole("navigation", { name: "Sections" });
    box = open(/Who or what is it/);
    await waitFor(() => expect(within(box).getByRole("option", { name: "Rubén" })).toBeInTheDocument());
    fireEvent.change(within(box).getByLabelText("Who for TRANSFERENCIA KENILITY"), { target: { value: "new" } });
    fireEvent.change(within(box).getByLabelText("New person's name"), { target: { value: "Napoles" } });
    fireEvent.click(within(box).getByRole("button", { name: "Add and save" }));
    expect(await screen.findByText("Added Napoles and saved who it is.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST" && c.url === "/api/people")!.body).toEqual({ name: "Napoles" });
  });

  it("settles a transfer whose other side isn't tracked, without a rule for general text", async () => {
    todo.sections.push({
      key: "transfers",
      title: "Transfers missing the other side",
      hint: "",
      count: 1,
      tasks: [
        {
          key: "transfer:8",
          kind: "transfer",
          title: "TRANSFERENCIA INTERNET",
          detail: "Sep 05 · Banco Pichincha",
          amount: "-150.00",
          on: "2026-09-05",
          link: "/review",
          data: { transaction_id: 8, merchant_key: "TRANSFERENCIA INTERNET", rule_ok: false },
        },
      ],
    });
    renderPage();
    await screen.findByRole("navigation", { name: "Sections" });
    const box = open(/Transfers missing the other side/);
    expect(within(box).getByText(/too general to remember/)).toBeInTheDocument();
    fireEvent.click(within(box).getByRole("button", { name: "Other side isn't in the app" }));
    expect(await screen.findByText("Done: it won't ask for the other side again.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.url === "/api/transfers/8/one-sided")).toBe(true);
  });

  it("stops counting a duplicate, or saves today's value", async () => {
    renderPage();
    await screen.findByRole("navigation", { name: "Sections" });
    const box = open(/Out-of-date values/);
    fireEvent.change(within(box).getByLabelText("Today's value of Stock Market"), { target: { value: "1,500.50" } });
    fireEvent.click(within(box).getByRole("button", { name: "Save value" }));
    expect(await screen.findByText("Saved today's value of Stock Market.")).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/holdings/3/values")!.body).toMatchObject({ amount: "1500.50" });
  });

  it("pauses a duplicate workbook value", async () => {
    renderPage();
    await screen.findByRole("navigation", { name: "Sections" });
    const box = open(/Out-of-date values/);
    fireEvent.click(within(box).getByRole("button", { name: "Stop counting it" }));
    expect(await screen.findByText(/Stopped counting Stock Market/)).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/holdings/3")!.body).toEqual({ is_active: false });
  });

  it("saves a suggested rule with another category, or says no", async () => {
    todo.sections.push({
      key: "suggestions",
      title: "Suggestions",
      hint: "",
      count: 2,
      tasks: [
        {
          key: "rule:UBER",
          kind: "rule",
          title: "Rule: UBER",
          detail: "→ Taxi · you chose it 3 times",
          amount: null,
          on: null,
          link: "/settings",
          data: { pattern: "UBER", category_id: 9, person: null },
        },
        {
          key: "bill:NETFLIX",
          kind: "bill",
          title: "Bill: NETFLIX",
          detail: "every 1 month",
          amount: "-15.49",
          on: null,
          link: "/recurring",
          data: {},
        },
      ],
    });
    renderPage();
    await screen.findByRole("navigation", { name: "Sections" });
    const box = open(/Suggestions/);
    pickCategory(within(box).getByRole("combobox", { name: /Different category for UBER/ }), "Sal", "Salary");
    await screen.findByText(/Rule saved/);
    expect(calls.find((c) => c.url === "/api/merchant-rules")!.body).toMatchObject({ pattern: "UBER", category_id: 2 });
    fireEvent.click(within(box).getByRole("button", { name: "Not a bill" }));
    expect(await screen.findByText("Fine, it won't suggest that bill again.")).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/todo/dismiss")!.body).toEqual({ key: "bill:NETFLIX" });
  });

  it("confirms a loan installment", async () => {
    todo.sections.push({
      key: "loans",
      title: "Loan payments to confirm",
      hint: "",
      count: 1,
      tasks: [
        {
          key: "loan:5:41",
          kind: "loan",
          title: "Did you pay BIESS installment 41?",
          detail: "November 2026",
          amount: "-3580.55",
          on: "2026-11-01",
          link: "/debt",
          data: { holding_id: 5, number: 41 },
        },
      ],
    });
    renderPage();
    await screen.findByRole("navigation", { name: "Sections" });
    const box = open(/Loan payments to confirm/);
    fireEvent.click(within(box).getByRole("button", { name: "Yes, paid" }));
    expect(await screen.findByText("Marked paid. The balance is now 98,000.00.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.url === "/api/holdings/5/installments/41/paid")).toBe(true);
  });

  it("says all clear when nothing is left", async () => {
    todo = { today: "2026-11-08", total: 0, sections: [] };
    renderPage();
    expect(await screen.findByText("All clear")).toBeInTheDocument();
  });
});
