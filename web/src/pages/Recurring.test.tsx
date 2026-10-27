import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { GridCell, GridRow, RecurringEntry, RecurringGrid, RecurringTemplate, Txn } from "../api";
import RecurringPage, { cellValue, totals } from "./Recurring";

const MONTHS = Array.from({ length: 12 }, (_, i) => `2026-${String(i + 1).padStart(2, "0")}-01`);
const cell = (i: number, over: Partial<GridCell> = {}): GridCell => ({
  month: MONTHS[i],
  entry_id: null,
  expected: null,
  actual: null,
  lines: 0,
  status: "none",
  is_override: false,
  notes: null,
  ...over,
});
const row = (id: number, name: string, type: GridRow["type"], group: string, cells: GridCell[]): GridRow => ({
  template_id: id,
  name,
  type,
  group,
  category_path: null,
  is_active: true,
  cells,
});

const salary = row(
  1,
  "Salary",
  "income",
  "Salaries",
  MONTHS.map((_, i) =>
    i < 6
      ? cell(i, { entry_id: 100 + i, expected: "5000", actual: "5100", lines: 1, status: "matched" })
      : cell(i, { entry_id: 100 + i, expected: "5000", status: "planned" }),
  ),
);
const condo = row(
  2,
  "Condo Fee",
  "expense",
  "Housing",
  MONTHS.map((_, i) =>
    i === 6
      ? cell(i, { entry_id: 207, expected: "-300", status: "planned", is_override: true })
      : i === 7
        ? cell(i, { entry_id: 208, expected: "-269", status: "skipped" })
        : i === 8
          ? cell(i, { expected: "-269", status: "not_generated" })
          : cell(i, { entry_id: 200 + i, expected: "-269", actual: "-269", lines: 1, status: "matched" }),
  ),
);
let grid: RecurringGrid;
let calls: { method: string; url: string; body?: unknown }[];
const json = (v: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(v), { status }));

const TEMPLATE: RecurringTemplate = {
  template_id: 2,
  name: "Condo Fee",
  category_id: 3,
  category_path: "Housing / Condo Fee",
  type: "expense",
  amount: "269",
  amounts: [{ from_month: "2026-01-01", amount: "269" }],
  start_month: "2026-01-01",
  end_month: null,
  account_id: null,
  account_name: null,
  person: null,
  match_pattern: null,
  tolerance_pct: "10.00",
  is_active: true,
  sort_order: 2,
  source: "manual",
  group: "Housing",
  notes: null,
};
const line = (id: number, description: string, amount: string): Txn => ({
  transaction_id: id,
  txn_date: "2026-07-05",
  post_date: null,
  cash_month: "2026-07-01",
  account_id: 5,
  account_name: "Produbanco Ahorros",
  description,
  merchant: null,
  amount,
  type: "expense",
  category_id: 3,
  category_path: "Housing / Condo Fee",
  person: null,
  country: "EC",
  source: "statement",
  statement_file_id: 1,
  notes: null,
  parent_transaction_id: null,
  parts: 0,
  category_source: "rule",
});
const ENTRY: RecurringEntry = {
  entry_id: 207,
  template_id: 2,
  template_name: "Condo Fee",
  month: "2026-07-01",
  amount: "-300",
  template_amount: "-269",
  is_override: true,
  status: "planned",
  notes: null,
  tolerance: "30",
  lines: [line(1, "PAGO CONDOMINIO", "-300.00")],
  candidates: [line(2, "DEBITO VISA", "-40.00")],
};

beforeEach(() => {
  calls = [];
  grid = { year: 2026, months: MONTHS, excel_months: MONTHS.slice(0, 6), rows: [salary, condo] };
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url.startsWith("/api/recurring/grid")) return json(grid);
      if (url === "/api/recurring/templates" && method === "GET") return json([TEMPLATE]);
      if (url === "/api/recurring/templates" && method === "POST")
        return json({ ...TEMPLATE, template_id: 9, name: "Phone", start_month: "2026-10-01" }, 201);
      if (url === "/api/recurring/templates/2" && method === "PATCH")
        return json({ ...TEMPLATE, name: "Condo" });
      if (url === "/api/recurring/templates/2" && method === "DELETE")
        return Promise.resolve(new Response(null, { status: 204 }));
      if (url === "/api/recurring/templates/2/amount") return json({ count: 3 });
      if (url === "/api/recurring/generate") return json({ count: 2 });
      if (url === "/api/recurring/copy") return json({ count: 4 });
      if (url === "/api/recurring/match") return json({ count: 0 });
      if (url === "/api/recurring/entries/207" && method === "GET") return json(ENTRY);
      if (url === "/api/recurring/entries/207" && method === "PATCH") {
        const b = JSON.parse(String(init!.body));
        return json({
          ...ENTRY,
          ...(b.status ? { status: b.status } : {}),
          amount: b.amount ? `-${b.amount}` : ENTRY.amount,
        });
      }
      if (url === "/api/recurring/entries/207/lines") return json(ENTRY);
      if (url.startsWith("/api/recurring/lines/"))
        return Promise.resolve(new Response(null, { status: 204 }));
      if (url.startsWith("/api/recurring/excel-rows"))
        return json([
          {
            name: "Salary",
            group: "Salaries",
            label: "Salary",
            block: "income",
            category_id: 1,
            category_path: "Salary",
            type: "income",
            months: 12,
            latest: "5000",
            suggested: true,
            exists: false,
          },
          {
            name: "Travel",
            group: "Others",
            label: "Travel",
            block: "expense",
            category_id: 4,
            category_path: "Travel",
            type: "expense",
            months: 1,
            latest: "129",
            suggested: false,
            exists: false,
          },
          {
            name: "Condo Fee",
            group: "Others",
            label: "Condo Fee",
            block: "expense",
            category_id: 3,
            category_path: "Housing",
            type: "expense",
            months: 12,
            latest: "269",
            suggested: false,
            exists: true,
          },
        ]);
      if (url === "/api/recurring/from-excel") return json({ templates: 2, entries: 13, linked: 6 });
      if (url === "/api/categories")
        return json([
          {
            category_id: 3,
            parent_id: null,
            name: "Housing",
            kind: "expense",
            color: null,
            is_fixed: true,
            is_active: true,
            sort_order: 0,
            children: [],
          },
        ]);
      if (url === "/api/accounts") return json([{ account_id: 5, name: "Produbanco Ahorros" }]);
      return json({ detail: "not found" }, 404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderAt(path = "/recurring?year=2026") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <RecurringPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("grid totals", () => {
  it("counts paid lines, else what is expected; skipped months count nothing", () => {
    expect(cellValue(cell(0, { status: "matched", expected: "-1", actual: "-2" }))).toBe(-2);
    expect(cellValue(cell(0, { status: "planned", expected: "-1" }))).toBe(-1);
    expect(cellValue(cell(0, { status: "skipped", expected: "-1" }))).toBe(0);
    const t = totals([salary, condo]);
    expect([t.income[0], t.out[0], t.left[0]]).toEqual([5100, 269, 4831]);
    expect([t.out[6], t.out[7], t.out[8]]).toEqual([300, 0, 0]);
    expect(totals([]).income).toHaveLength(12);
  });
});

describe("Recurring page", () => {
  it("shows the year like the sheet, with paid, expected and skipped cells", async () => {
    renderAt();
    const table = await screen.findByRole("table", { name: "Recurring items in 2026, by month" });
    expect(within(table).getByText("Income")).toBeInTheDocument();
    expect(
      within(table).getByRole("button", { name: "Salary, January 2026: 5,100.00, paid" }),
    ).toBeInTheDocument();
    const jul = within(table).getByRole("button", { name: "Condo Fee, July 2026: 300.00, expected" });
    expect(jul).toHaveTextContent("• 300.00");
    expect(
      within(table).getByRole("button", { name: "Condo Fee, August 2026: skipped, skipped" }),
    ).toBeInTheDocument();
    expect(
      within(table).getByRole("button", { name: "Condo Fee, September 2026: not generated" }),
    ).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: /^Left/ })).toHaveTextContent("4,831.00");
    expect(within(table).getAllByText("sheet")).toHaveLength(6);
  });

  it("changes one month, from a month on, skips it and moves lines", async () => {
    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: "Condo Fee, July 2026: 300.00, expected" }));
    const panel = await screen.findByRole("region", { name: "Condo Fee in July 2026" });
    expect(await within(panel).findByText(/the template says 269.00/)).toBeInTheDocument();
    fireEvent.change(within(panel).getByLabelText("This month only"), { target: { value: "310" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Save Jul" }));
    expect(await screen.findByText("Condo Fee, July 2026: 310.00 expected.")).toBeInTheDocument();
    fireEvent.change(within(panel).getByLabelText("From July 2026 on"), { target: { value: "280" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Change from Jul on" }));
    expect(await screen.findByText("Condo Fee: 280.00 from July 2026 on.")).toBeInTheDocument();
    expect(calls.find((c) => c.url.endsWith("/amount"))?.body).toEqual({
      from_month: "2026-07-01",
      amount: "280",
    });
    fireEvent.click(within(panel).getByRole("button", { name: "Back to the template amount" }));
    await waitFor(() => expect(calls.some((c) => (c.body as { reset?: boolean })?.reset)).toBe(true));
    fireEvent.click(within(panel).getByRole("button", { name: "Skip Jul (doesn’t happen)" }));
    expect(await screen.findByText("Condo Fee skipped in July 2026.")).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "Unlink PAGO CONDOMINIO on Jul 5" }));
    expect(await screen.findByText("Line unlinked.")).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "Link DEBITO VISA on Jul 5" }));
    expect(await screen.findByText("Line linked.")).toBeInTheDocument();
    expect(within(panel).getByText(/Tip: an account or a description pattern/)).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("region", { name: "Condo Fee in July 2026" })).toBeNull();
  });

  it("generates a month, from a cell or the toolbar, copies forward and matches again", async () => {
    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: "Condo Fee, September 2026: not generated" }));
    const panel = await screen.findByRole("region", { name: "Condo Fee in September 2026" });
    expect(within(panel).getByText("Not generated yet: the template expects 269.00.")).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "Generate September 2026" }));
    expect(await screen.findByText("September 2026 generated.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Month"), { target: { value: "2026-11" } });
    fireEvent.click(screen.getByRole("button", { name: "Generate November" }));
    expect(await screen.findByText("November 2026: 2 recurring items generated.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy Nov forward" }));
    const form = screen.getByRole("form", { name: "Copy a month" });
    fireEvent.change(within(form).getByLabelText("To"), { target: { value: "2027-02" } });
    fireEvent.click(within(form).getByRole("button", { name: "Copy to these months" }));
    expect(await screen.findByText("Copied November 2026 to 4 cells.")).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/recurring/copy")?.body).toEqual({
      from_month: "2026-11-01",
      to_start: "2026-12-01",
      to_end: "2027-02-01",
    });
    fireEvent.click(screen.getByRole("button", { name: "Match lines again" }));
    expect(await screen.findByText("No new lines to link.")).toBeInTheDocument();
  });

  it("adds a template and edits, pauses and removes one", async () => {
    renderAt();
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "New template" }));
    const form = screen.getByRole("form", { name: "New template" });
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: " Phone " } });
    fireEvent.change(within(form).getByLabelText("Amount each month"), { target: { value: "27.12" } });
    fireEvent.change(await within(form).findByLabelText("Category"), { target: { value: "3" } });
    fireEvent.change(within(form).getByLabelText("Account (optional)"), { target: { value: "5" } });
    fireEvent.change(within(form).getByLabelText("Description contains (optional)"), {
      target: { value: "CONECEL" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Add template" }));
    expect(
      await screen.findByText("Phone added from October 2026. Generate a month to expect it."),
    ).toBeInTheDocument();
    expect(
      calls.find((c) => c.method === "POST" && c.url === "/api/recurring/templates")?.body,
    ).toMatchObject({
      name: "Phone",
      category_id: 3,
      account_id: 5,
      match_pattern: "CONECEL",
      amount: "27.12",
    });

    fireEvent.click(screen.getByRole("button", { name: "Condo Fee" }));
    const editor = await screen.findByRole("region", { name: "Template Condo Fee" });
    expect(editor).toHaveTextContent("269.00 from Jan 2026");
    fireEvent.change(within(editor).getByLabelText("Last month (optional)"), {
      target: { value: "2026-12" },
    });
    fireEvent.click(within(editor).getByRole("button", { name: "Save Condo Fee" }));
    expect(await screen.findByText("Condo saved.")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ end_month: "2026-12-01" });
    fireEvent.click(within(editor).getByRole("button", { name: "Pause it" }));
    await waitFor(() =>
      expect(calls.some((c) => (c.body as { is_active?: boolean })?.is_active === false)).toBe(true),
    );
    fireEvent.click(within(editor).getByRole("button", { name: "Remove…" }));
    fireEvent.click(within(editor).getByRole("button", { name: "Remove Condo Fee and its months" }));
    expect(await screen.findByText("Condo Fee removed, with its months.")).toBeInTheDocument();
  });

  it("creates templates from the sheet's ticked rows", async () => {
    grid = { ...grid, rows: [] };
    renderAt();
    fireEvent.click(await screen.findByRole("button", { name: "Choose rows from the 2026 sheet" }));
    const picker = await screen.findByRole("region", { name: "Rows of the 2026 sheet" });
    const salaryBox = await within(picker).findByRole("checkbox", { name: /Salary/ });
    expect(salaryBox).toBeChecked();
    expect(within(picker).getByRole("checkbox", { name: /Condo Fee/ })).toBeDisabled();
    fireEvent.click(within(picker).getByRole("checkbox", { name: /Travel/ }));
    fireEvent.click(within(picker).getByRole("button", { name: "Create 2 templates" }));
    expect(
      await screen.findByText(
        "2 templates created; 2026 filled with 13 months, 6 linked to the sheet’s lines.",
      ),
    ).toBeInTheDocument();
    expect(calls.find((c) => c.url === "/api/recurring/from-excel")?.body).toEqual({
      year: 2026,
      names: ["Salary", "Travel"],
    });
  });

  it("moves between years and reports errors", async () => {
    renderAt();
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "2027 →" }));
    await waitFor(() => expect(calls.some((c) => c.url === "/api/recurring/grid?year=2027")).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "← 2026" }));
    vi.mocked(fetch).mockImplementationOnce(() => json({ detail: "boom" }, 500));
    fireEvent.click(await screen.findByRole("button", { name: "Match lines again" }));
    expect(await screen.findByText("boom")).toBeInTheDocument();
  });
});
