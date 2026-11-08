import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
      if (url === "/api/people") return json([{ counterparty_id: 4, name: "Rubén", is_active: true }]);
      if (url === "/api/review/resolve") return json({ categorized: 3, rule_id: 11, also_by_rule: 0 });
      if (url === "/api/transactions/7") return json({ transaction_id: 7 });
      if (url === "/api/merchant-rules") return json({ rule_id: 12, pattern: "X", category_path: "Income / Salary" }, 201);
      if (url === "/api/review/who") return json({ transaction_id: 7 });
      if (url === "/api/holdings/3") return json({ holding_id: 3 });
      return json({ detail: "not here" }, 404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

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

describe("To do", () => {
  it("lists every section with its count and a way to act", async () => {
    renderPage();
    const nav = await screen.findByRole("navigation", { name: "Sections" });
    expect(within(nav).getByText("Needs a category")).toBeInTheDocument();
    const books = screen.getByRole("region", { name: "Statements, imports and bills" });
    expect(within(books).getByRole("link", { name: "Open" })).toHaveAttribute("href", "/import");
    expect(within(books).getByText("And 1 more: they show here as you finish these.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "statement" })).toHaveAttribute("href", expect.stringContaining("9"));
  });

  it("categorizes a merchant and saves the rule", async () => {
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
  });

  it("calls a transfer income, or gives it a person", async () => {
    renderPage();
    const box = await screen.findByRole("region", { name: "Who or what is it" });
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
    await waitFor(() => expect(within(box).getByRole("option", { name: "Rubén" })).toBeInTheDocument());
    fireEvent.change(within(box).getByLabelText("Who for TRANSFERENCIA KENILITY"), { target: { value: "4" } });
    expect(await screen.findByText("Saved who it is.")).toBeInTheDocument();
  });

  it("pauses a duplicate workbook value", async () => {
    renderPage();
    const box = await screen.findByRole("region", { name: "Out-of-date values" });
    fireEvent.click(within(box).getByRole("button", { name: "Pause it" }));
    expect(await screen.findByText(/Paused Stock Market/)).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/holdings/3")!.body).toEqual({ is_active: false });
  });

  it("says all clear when nothing is left", async () => {
    todo = { today: "2026-11-08", total: 0, sections: [] };
    renderPage();
    expect(await screen.findByText("All clear")).toBeInTheDocument();
  });
});
