import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ImportPage from "./Import";

const PREVIEW = {
  file_name: "Cash Flow.xlsx",
  file_sha256: "abc",
  already_loaded: false,
  first_month: "2019-08-01",
  last_month: "2026-06-01",
  months: 83,
  actual_rows: 1180,
  plan_rows: 71,
  plan_months: ["2026-07-01"],
  years: [{ year: 2026, months: 6, income: "60000", outflows: "50000" }],
  mismatches: [
    {
      month: "2025-11-01",
      sheet: "Cash Flow 2025",
      income_rows: "1",
      income_workbook: "1",
      expense_rows: "10300",
      expense_workbook: "10240",
      left_out: ["Aliquota Ofi 60.00"],
      typed_total: false,
      explained: true,
    },
    {
      month: "2019-09-01",
      sheet: "Cash Flow 2021",
      income_rows: "15000",
      income_workbook: "9000",
      expense_rows: "2000",
      expense_workbook: "2000",
      left_out: [],
      typed_total: true,
      explained: false,
    },
  ],
  unmapped: [],
  mapping: [
    {
      block: "expense",
      group: "Others",
      label: "Killa Guardería",
      type: "expense",
      category: "Pets/Pet Daycare",
      person: "Joint",
      months: 20,
      total: "4000.00",
      review: "Killa: your dog?",
    },
  ],
  snapshots: [{ as_of: "2026-01-31", name: "BIESS", kind: "liability", amount: "30000.55", notes: "x" }],
  side_cells: 20,
};
let calls: string[];

function stub(previewBody: object, loadStatus = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      calls.push(url);
      if (url.endsWith("/preview")) return Promise.resolve(new Response(JSON.stringify(previewBody)));
      if (loadStatus !== 200)
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "This exact workbook is already loaded." }), {
            status: loadStatus,
          }),
        );
      return Promise.resolve(
        new Response(
          JSON.stringify({
            load_id: 1,
            transactions: 1180,
            budget_rows: 60,
            snapshots: 8,
            raw_cells: 1271,
            replaced_transactions: 0,
          }),
        ),
      );
    }),
  );
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ImportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const pick = () => {
  const file = new File(["x"], "Cash Flow.xlsx");
  fireEvent.change(screen.getByLabelText("Workbook (.xlsx)"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "Preview" }));
};

beforeEach(() => (calls = []));
afterEach(() => vi.unstubAllGlobals());

describe("Import: Excel history", () => {
  it("previews, shows what needs checking, then loads", async () => {
    stub(PREVIEW);
    renderPage();
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();
    pick();
    expect(await screen.findByText(/83 months/)).toBeInTheDocument();
    expect(screen.getByText(/Killa: your dog\?/)).toBeInTheDocument();
    expect(screen.getByText(/left out Aliquota Ofi 60.00/)).toBeInTheDocument();
    expect(screen.getByText(/1 with a typed-in total/)).toBeInTheDocument();
    expect(screen.getByText(/BIESS/)).toBeInTheDocument();
    expect(calls).toEqual(["/api/history/excel/preview"]);

    fireEvent.click(screen.getByRole("button", { name: "Load history" }));
    expect(await screen.findByText("History loaded.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See the Overview" })).toHaveAttribute("href", "/");
  });

  it("blocks loading when rows have no category or the file is already loaded", async () => {
    stub({ ...PREVIEW, unmapped: [{ sheet: "Cash Flow 2026", cell: "B8", label: "Lottery", value: "10" }] });
    renderPage();
    pick();
    expect(await screen.findByText(/Lottery/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load history" })).toBeDisabled();
  });

  it("shows the API message when loading fails", async () => {
    stub(PREVIEW, 409);
    renderPage();
    pick();
    fireEvent.click(await screen.findByRole("button", { name: "Load history" }));
    expect(await screen.findByText("This exact workbook is already loaded.")).toBeInTheDocument();
  });
});
