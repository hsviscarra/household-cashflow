import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MonthlyReport } from "../api";
import { ExportLinks } from "../components/ExportLinks";
import ReportPage, { writtenBy } from "./Report";

const flow = (net: string, rate: string | null = "0.25") => ({
  income: "3000",
  expenses: "2000",
  savings: "200",
  debt_payments: "50",
  net,
  savings_rate: rate,
});
const REPORT: MonthlyReport = {
  month: "2026-10-01",
  written_by: "claude",
  model: "claude-sonnet-5-5",
  generated_at: "2026-10-28T21:40:00",
  generated_by: "hernan@example.com",
  facts: {
    month: "2026-10",
    data: { complete: false, open: ["Bank A: no statement for October"] },
    cash_flow: { month: flow("750"), last_month: flow("600", "0.2"), average_3_months: flow("700") },
  },
  findings: [
    { title: "Net +750.00 in October", text: "Income 3,000.00.", tone: "good" },
    { title: "Dining up 150.00", text: "Dining 300.00.", tone: "bad" },
    { title: "October isn't complete", text: "1 thing open.", tone: "neutral" },
  ],
  notice: null,
};
const EXPORTS = [
  { key: "monthly_cashflow", title: "Monthly cash flow (spending view)", by: "year" },
  { key: "transactions", title: "Transactions", by: "month" },
];

function renderWith(routes: Record<string, unknown>, path = "/report") {
  const calls: { method: string; url: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url });
      const body = routes[`${method} ${url}`];
      if (body instanceof Response) return Promise.resolve(body);
      if (body === undefined)
        return Promise.resolve(new Response(JSON.stringify({ detail: "nope" }), { status: 404 }));
      return Promise.resolve(new Response(JSON.stringify(body)));
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ReportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

describe("monthly report", () => {
  it("says who wrote it", () => {
    expect(writtenBy(REPORT)).toMatch(
      /^Written by Claude \(claude-sonnet-5-5\) on Oct 28, 2026, 9:40 PM, for hernan/,
    );
    expect(writtenBy({ ...REPORT, written_by: "rules", model: null, generated_at: null })).toBe(
      "Written by rules (Claude is off), for hernan@example.com",
    );
  });

  it("shows the saved report: numbers, open items, findings and downloads", async () => {
    renderWith({
      "GET /api/reports": { months: ["2026-10-01", "2026-09-01"], claude: true },
      "GET /api/reports/2026-10": REPORT,
      "GET /api/exports": EXPORTS,
    });
    expect(await screen.findByRole("heading", { level: 1, name: "October 2026 report" })).toBeInTheDocument();
    const findings = await screen.findByRole("list", { name: "Findings" });
    const items = within(findings).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Good newsNet +750.00 in OctoberIncome 3,000.00.");
    expect(items[1]).toHaveTextContent("Needs attentionDining up 150.00");
    expect(items[2]).toHaveTextContent("Note");
    expect(screen.getByText("Net").nextSibling).toHaveTextContent("+750.00");
    expect(screen.getByText("3-month average")).toHaveTextContent("3-month average 700.00");
    expect(screen.getByText("Savings rate").parentElement).toHaveTextContent("Savings rate25%last month 20%");
    expect(screen.getByRole("list", { name: "Still open" })).toHaveTextContent(
      "Bank A: no statement for October",
    );
    expect(screen.getByRole("button", { name: "Regenerate" })).toBeInTheDocument();
    const downloads = await screen.findByRole("list", { name: "Downloads" });
    expect(within(downloads).getByRole("link", { name: "CSV of Transactions" })).toHaveAttribute(
      "href",
      "/api/exports/transactions.csv?month=2026-10",
    );
    expect(
      within(downloads).getByRole("link", { name: "Excel of Monthly cash flow (spending view)" }),
    ).toHaveAttribute("href", "/api/exports/monthly_cashflow.xlsx?year=2026");
  });

  it("writes a missing report, shows a notice, and switches months", async () => {
    const calls = renderWith(
      {
        "GET /api/reports": { months: ["2026-10-01", "2026-09-01"], claude: true },
        "GET /api/reports/2026-09": null,
        "POST /api/reports/2026-09/generate": {
          ...REPORT,
          month: "2026-09-01",
          written_by: "rules",
          model: null,
          notice: "Claude could not be reached. These findings are written by rules instead.",
          facts: { ...REPORT.facts, data: { complete: true, open: [] } },
        },
        "GET /api/exports": EXPORTS,
      },
      "/report?month=2026-09",
    );
    expect(
      await screen.findByText(/No report for September 2026 yet. Claude writes the findings/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Write the report with Claude" }));
    expect(await screen.findByText(/Claude could not be reached/)).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Still open" })).toBeNull();
    expect(calls.some((c) => c.method === "POST")).toBe(true);
    fireEvent.change(screen.getByLabelText("Month"), { target: { value: "2026-10" } });
    expect(await screen.findByRole("heading", { level: 1, name: "October 2026 report" })).toBeInTheDocument();
  });

  it("without Claude, without data, and on errors", async () => {
    renderWith({
      "GET /api/reports": { months: ["2026-10-01"], claude: false },
      "GET /api/reports/2026-10": null,
      "POST /api/reports/2026-10/generate": new Response(JSON.stringify({ detail: "Nothing is loaded" }), {
        status: 422,
      }),
      "GET /api/exports": new Response("{}", { status: 500 }),
    });
    expect(await screen.findByText(/Claude is off \(no API key\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Write the report" }));
    expect(await screen.findByText("Could not write the report: Nothing is loaded")).toBeInTheDocument();
    expect(await screen.findByText("Could not load the exports.")).toBeInTheDocument();
  });

  it("empty and failing", async () => {
    renderWith({ "GET /api/reports": { months: [], claude: false } });
    expect(await screen.findByText(/Nothing is loaded yet/)).toBeInTheDocument();
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
    renderWith({
      "GET /api/reports": new Response(JSON.stringify({ detail: "boom" }), { status: 500 }),
    });
    expect(await screen.findByText("Could not load the months: boom")).toBeInTheDocument();
    document.body.innerHTML = "";
    renderWith(
      {
        "GET /api/reports": { months: ["2026-10-01"], claude: false },
        "GET /api/reports/2026-10": new Response(JSON.stringify({ detail: "down" }), { status: 500 }),
        "GET /api/exports": EXPORTS,
      },
      "/report?month=2026-08",
    );
    expect(await screen.findByText("Could not load the report: nope")).toBeInTheDocument();
    expect(screen.getByLabelText("Month")).toHaveValue("2026-08");
  });

  it("export links", () => {
    render(<ExportLinks dataset="debt_cost" label="fees" year={2026} />);
    expect(screen.getByRole("link", { name: "CSV" })).toHaveAttribute(
      "href",
      "/api/exports/debt_cost.csv?year=2026",
    );
    render(<ExportLinks dataset="monthly_cash" label="all" />);
    expect(screen.getAllByRole("link", { name: "Excel" })[1]).toHaveAttribute(
      "href",
      "/api/exports/monthly_cash.xlsx",
    );
  });
});
