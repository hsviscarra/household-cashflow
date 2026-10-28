import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Sources, Statement } from "../api";
import { SourcesSection, monthChoices, sourcesLine } from "../components/SourcesSection";
import { StatementsCard, backlog } from "./ImportStatements";

const st = (id: number, over: Partial<Statement>): Statement => ({
  statement_file_id: id,
  file_name: `s${id}.pdf`,
  source: "capitalone",
  source_label: "Capital One",
  status: "detected",
  accounts: [{ account_id: 1, name: "Card", last4: "4003" }],
  account_match: "last4",
  last4_found: ["4003"],
  period_start: "2026-01-04",
  period_end: "2026-02-03",
  page_count: 3,
  size_bytes: 1000,
  uploaded_by: "hernan@example.com",
  uploaded_at: "2026-10-28T15:00:00",
  can_read: true,
  batch: null,
  ...over,
});
const LIST: Statement[] = [
  st(1, { period_start: "2026-03-04", period_end: "2026-04-03" }),
  st(2, { period_start: "2026-01-04", period_end: "2026-02-03" }),
  st(3, { batch: { batch_id: 30, status: "preview", tieout_ok: true }, period_end: "2026-02-03" }),
  st(4, { batch: { batch_id: 40, status: "preview", tieout_ok: false }, period_end: "2026-02-20" }),
  st(5, { batch: { batch_id: 50, status: "preview", tieout_ok: true }, period_end: "2026-03-03" }),
  st(6, { batch: { batch_id: 60, status: "approved", tieout_ok: true } }),
  st(7, { status: "needs_account", can_read: false }),
];

afterEach(() => vi.unstubAllGlobals());

function renderCard(statements: Statement[], fail: string[] = []) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url === "/api/accounts") return Promise.resolve(new Response("[]"));
      if (url === "/api/statements" && init?.method === "POST") return Promise.resolve(new Response("[]"));
      if (url === "/api/statements" && (init?.method ?? "GET") === "GET")
        return Promise.resolve(new Response(JSON.stringify(statements)));
      if (fail.some((f) => url.includes(f)))
        return Promise.resolve(new Response(JSON.stringify({ detail: "doesn't tie out" }), { status: 422 }));
      return Promise.resolve(new Response(JSON.stringify({ batch_id: 1, loaded: 1, skipped_duplicates: 0 })));
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <StatementsCard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return calls;
}

describe("backlog", () => {
  it("orders unread statements oldest first and groups the waiting ones by month", () => {
    const b = backlog(LIST);
    expect(b.unread.map((s) => s.statement_file_id)).toEqual([2, 1]);
    expect(b.months.map(([m, g]) => [m, g.ready.length, g.problems.length])).toEqual([
      ["2026-02", 1, 1],
      ["2026-03", 1, 0],
    ]);
  });

  it("reads all, oldest first, and approves a month", async () => {
    const calls = renderCard(LIST);
    const section = await screen.findByRole("region", { name: "Backlog" });
    fireEvent.click(within(section).getByRole("button", { name: "Read all (2)" }));
    expect(await within(section).findByText("Read 2 of 2.")).toBeInTheDocument();
    expect(calls.filter((c) => c.startsWith("POST"))).toEqual([
      "POST /api/statements/2/read",
      "POST /api/statements/1/read",
    ]);
    const months = within(section).getByRole("list", { name: "Waiting for approval" });
    expect(months).toHaveTextContent("February 2026: 1 ready, 1 doesn’t tie out (s4.pdf)");
    expect(within(months).getByRole("link", { name: "s4.pdf" })).toHaveAttribute(
      "href",
      "/import/batches/40",
    );
    fireEvent.click(within(months).getAllByRole("button", { name: "Approve 1" })[0]);
    expect(await within(section).findByText("Approved 1 of 1.")).toBeInTheDocument();
    expect(calls).toContain("POST /api/batches/30/approve");
  });

  it("lists what failed and hides with nothing to do", async () => {
    renderCard([st(2, {})], ["/statements/2/read"]);
    const section = await screen.findByRole("region", { name: "Backlog" });
    fireEvent.click(within(section).getByRole("button", { name: "Read all (1)" }));
    expect(await within(section).findByText("Read 0 of 1.")).toBeInTheDocument();
    expect(within(section).getByRole("list", { name: "Problems" })).toHaveTextContent(
      "s2.pdf: doesn't tie out",
    );
  });

  it("is absent when nothing waits", async () => {
    renderCard([st(6, { batch: { batch_id: 60, status: "approved", tieout_ok: true } })]);
    await screen.findByText("s6.pdf");
    expect(screen.queryByRole("region", { name: "Backlog" })).toBeNull();
  });

  it("uploads more than 50 files in chunks", async () => {
    const calls = renderCard([]);
    const files = Array.from(
      { length: 51 },
      (_, i) => new File(["%PDF"], `f${i}.pdf`, { type: "application/pdf" }),
    );
    fireEvent.change(screen.getByLabelText("Statement PDFs"), { target: { files } });
    fireEvent.click(screen.getByRole("button", { name: "Upload statements" }));
    await vi.waitFor(() => expect(calls.filter((c) => c === "POST /api/statements")).toHaveLength(2));
  });
});

const SOURCES: Sources = {
  statements_from: "2026-01-01",
  workbook_first: "2025-11-01",
  workbook_last: "2026-06-01",
  check: [
    {
      month: "2026-01-01",
      workbook_income: "8000",
      statements_income: "7900",
      workbook_spending: "1000",
      statements_spending: "750",
      statement_lines: 40,
      groups: [{ group: "Groceries", workbook: "500", statements: "250", difference: "-250" }],
    },
  ],
};

function renderSources(body: Sources, put?: Response) {
  const calls: { method: string; body?: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((_url: string, init?: RequestInit) => {
      calls.push({ method: init?.method ?? "GET", body: init?.body as string | undefined });
      if (init?.method === "PUT") return Promise.resolve(put ?? new Response(JSON.stringify(body)));
      return Promise.resolve(new Response(JSON.stringify(body)));
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <SourcesSection />
    </QueryClientProvider>,
  );
  return calls;
}

describe("where the numbers come from", () => {
  it("words and month choices", () => {
    expect(sourcesLine(SOURCES)).toBe(
      "From January 2026 the statements count; before it, the Cash Flow workbook.",
    );
    expect(sourcesLine({ ...SOURCES, statements_from: null })).toBe(
      "The Cash Flow workbook counts through June 2026; statements count after it.",
    );
    expect(sourcesLine({ ...SOURCES, statements_from: null, workbook_last: null })).toBe(
      "Statements count for every month.",
    );
    const months = monthChoices(SOURCES, new Date(2026, 1, 15));
    expect(months).toEqual(["2026-02-01", "2026-01-01", "2025-12-01", "2025-11-01"]);
    expect(monthChoices({ ...SOURCES, workbook_first: null }, new Date(2026, 1, 15))).toEqual([
      "2026-02-01",
      "2026-01-01",
    ]);
  });

  it("shows the check and saves a new month", async () => {
    const calls = renderSources(SOURCES);
    const section = await screen.findByRole("region", { name: "Where the numbers come from" });
    const check = within(section).getByRole("list", { name: "Workbook vs statements" });
    expect(check).toHaveTextContent("January 2026Spending: workbook 1,000.00 · statements 750.00 (−250.00)");
    expect(check).toHaveTextContent("Income: workbook 8,000.00 · statements 7,900.00 · 40 statement lines");
    expect(within(check).getByRole("row", { name: /Groceries/ })).toHaveTextContent(
      "Groceries500.00250.00−250.00",
    );
    const save = within(section).getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    fireEvent.change(within(section).getByLabelText("Statements count from"), {
      target: { value: "2025-12" },
    });
    fireEvent.click(save);
    await vi.waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(JSON.parse(calls.find((c) => c.method === "PUT")!.body!)).toEqual({
      statements_from: "2025-12-01",
    });
  });

  it("clears the month, and reports errors", async () => {
    const calls = renderSources(
      SOURCES,
      new Response(JSON.stringify({ detail: "That month hasn't started yet." }), { status: 422 }),
    );
    const section = await screen.findByRole("region", { name: "Where the numbers come from" });
    fireEvent.change(within(section).getByLabelText("Statements count from"), { target: { value: "" } });
    fireEvent.click(within(section).getByRole("button", { name: "Save" }));
    expect(await within(section).findByText("That month hasn't started yet.")).toBeInTheDocument();
    expect(JSON.parse(calls.find((c) => c.method === "PUT")!.body!)).toEqual({ statements_from: null });
  });

  it("without a check, and when loading fails", async () => {
    renderSources({ ...SOURCES, check: [] });
    const section = await screen.findByRole("region", { name: "Where the numbers come from" });
    expect(within(section).queryByRole("list")).toBeNull();
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("{}", { status: 500 }))),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SourcesSection />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Could not load where the numbers come from.")).toBeInTheDocument();
  });
});
