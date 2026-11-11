import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DataStatus, MonthStatus } from "../api";
import StatusPage, { Arrivals, downloadText, missingGaps, summary } from "./Status";

const ACCOUNTS = [
  { account_id: 1, name: "Checking", kind: "checking", owner: "Joint" },
  { account_id: 2, name: "Card", kind: "credit_card", owner: "Hernan" },
];
const month = (
  m: string,
  items: MonthStatus["items"],
  cover: ["full" | "partial" | "none", number][],
): MonthStatus => ({
  month: m,
  source: "statements",
  complete: items.length === 0,
  items,
  coverage: cover.map(([state, covered], i) => ({
    account_id: i + 1,
    state,
    covered_days: covered,
    days: 31,
  })),
});
const STATUS: DataStatus = {
  today: "2026-08-10",
  excel_through: "2026-06-01",
  accounts: ACCOUNTS,
  months: [
    month(
      "2026-08-01",
      [
        { kind: "statement", text: "Card: no statement for Aug 4–10", link: "/import", count: 1 },
        { kind: "uncategorized", text: "2 lines need a category", link: "/review?month=2026-08", count: 2 },
        { kind: "import", text: "aug.pdf waits for approval", link: "/import/batches/7", count: 1 },
      ],
      [
        ["full", 31],
        ["partial", 3],
      ],
    ),
    month(
      "2026-07-01",
      [],
      [
        ["full", 31],
        ["full", 31],
      ],
    ),
    { month: "2026-06-01", source: "excel", complete: true, items: [], coverage: [] },
  ],
  loads: [
    {
      loaded_at: "2026-08-09T15:00:00",
      source: "statement",
      file_name: "jul.pdf",
      rows: 12,
      loaded_by: "hernan@example.com",
    },
    {
      loaded_at: "2026-07-01T10:00:00",
      source: "excel_history",
      file_name: "Cash Flow.xlsx",
      rows: 900,
      loaded_by: "local",
    },
  ],
};

function renderWith(body: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      url === "/api/sources"
        ? Promise.resolve(
            new Response(
              JSON.stringify({ statements_from: null, workbook_first: null, workbook_last: null, check: [] }),
            ),
          )
        : Promise.resolve(new Response(JSON.stringify(body), { status })),
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <StatusPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("Data Status", () => {
  it("says complete or how many things are missing", () => {
    expect(summary(STATUS.months[0])).toBe("3 things missing");
    expect(summary({ ...STATUS.months[0], items: STATUS.months[0].items.slice(0, 1), complete: false })).toBe(
      "1 thing missing",
    );
    expect(summary(STATUS.months[1])).toBe("Complete");
  });

  it("leads with the latest month and links each missing item to its fix", async () => {
    renderWith(STATUS);
    expect(
      await screen.findByRole("heading", { level: 1, name: "August 2026: 3 things missing" }),
    ).toBeInTheDocument();
    const months = screen.getByRole("list", { name: "Months" });
    const aug = within(months).getByRole("listitem", { name: "August 2026" });
    expect(
      within(aug).getByRole("link", { name: "Upload for Card: no statement for Aug 4–10" }),
    ).toHaveAttribute("href", "/import");
    expect(within(aug).getByRole("link", { name: "Review for 2 lines need a category" })).toHaveAttribute(
      "href",
      "/review?month=2026-08",
    );
    expect(within(aug).getByRole("link", { name: /Open the import/ })).toHaveAttribute(
      "href",
      "/import/batches/7",
    );
    const jul = within(months).getByRole("listitem", { name: "July 2026" });
    expect(jul).toHaveTextContent("Complete");
    expect(jul.querySelector("details")?.open).toBe(false);
    fireEvent.click(within(jul).getByText("July 2026"));
    expect(screen.getByText("Through June 2026: complete, from the Cash Flow sheet.")).toBeInTheDocument();
  });

  it("warns when the Gmail script has gone silent, and stays quiet when it checks in", async () => {
    const note = "The Gmail script last checked in 3 days ago (Nov 8): statements by email aren't arriving.";
    const { unmount } = renderWith({
      ...STATUS,
      script: { state: "silent", last_seen: "2026-11-08T11:00:00", note },
    });
    expect(await screen.findByText(note)).toBeInTheDocument();
    unmount();
    renderWith({
      ...STATUS,
      script: { state: "ok", last_seen: "2026-11-11T11:00:00", note: "Checked in Nov 11." },
    });
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByText("Checked in Nov 11.")).not.toBeInTheDocument();
  });

  it("shows coverage by account and the load log", async () => {
    renderWith(STATUS);
    const table = await screen.findByRole("table", { name: "Statement coverage by account and month" });
    const card = within(table).getByRole("row", { name: /^Card/ });
    expect(card).toHaveTextContent("Full");
    expect(card).toHaveTextContent("Part 3/31");
    const log = screen.getByRole("table", { name: "Latest loads" });
    expect(within(log).getByText("jul.pdf")).toBeInTheDocument();
    expect(within(log).getByText("Cash Flow sheet")).toBeInTheDocument();
  });

  it("handles nothing loaded and errors", async () => {
    const { unmount } = renderWith({ ...STATUS, excel_through: null, months: [], loads: [] });
    expect(await screen.findByText("Nothing loaded yet.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Data Status");
    expect(screen.queryByRole("table", { name: /coverage/ })).toBeNull();
    unmount();
    renderWith({ detail: "boom" }, 500);
    expect(await screen.findByText("Could not load the data status: boom")).toBeInTheDocument();
  });
});

describe("Data Status: statement periods", () => {
  const TIMELINE = [
    {
      account_id: 2,
      name: "Card",
      closed_on: null,
      start_day: 4,
      statements: [
        {
          statement_file_id: 1,
          file_name: "may.pdf",
          start: "2026-05-04",
          end: "2026-06-03",
          state: "loaded" as const,
          batch_id: 10,
        },
        {
          statement_file_id: 3,
          file_name: "jul.pdf",
          start: "2026-07-04",
          end: "2026-08-03",
          state: "waiting" as const,
          batch_id: 12,
        },
      ],
      gaps: [
        {
          start: "2026-06-04",
          end: "2026-07-03",
          due: null,
          closes: ["2026-07-03"],
          files: ["Statement_072026_4003.pdf"],
        },
        { start: "2026-08-04", end: "2026-08-10", due: "2026-09-03" },
      ],
    },
    {
      account_id: 1,
      name: "Checking",
      closed_on: "2026-09-15",
      start_day: 1,
      statements: [
        {
          statement_file_id: 4,
          file_name: "aug.pdf",
          start: "2026-08-01",
          end: "2026-08-31",
          state: "not_read" as const,
          batch_id: null,
        },
      ],
      gaps: [],
    },
  ];

  it("lists each account's statements and the exact days to download", async () => {
    renderWith({ ...STATUS, statements: TIMELINE });
    const list = await screen.findByRole("list", { name: "Statement periods by account" });
    const card = within(list).getByRole("listitem", { name: "Card" });
    expect(card).toHaveTextContent("statements start on the 4th");
    expect(card).toHaveTextContent("1 gap to fill");
    expect(card.querySelector("details")?.open).toBe(true);
    const rows = within(card)
      .getAllByRole("listitem")
      .map((r) => r.textContent);
    expect(rows).toEqual([
      expect.stringContaining("May 4, 2026 – Jun 3, 2026"),
      expect.stringContaining(
        "Jun 4, 2026 – Jul 3, 2026Download the statement closing Jul 3, 2026Statement_072026_4003.pdf",
      ),
      expect.stringContaining("Jul 4, 2026 – Aug 3, 2026"),
      "Aug 4, 2026 – Aug 10, 2026Current cycle: the bank issues it around Sep 3, 2026",
    ]);
    expect(within(card).getByRole("link", { name: "Waiting for approval" })).toHaveAttribute(
      "href",
      "/import/batches/12",
    );
    const checking = within(list).getByRole("listitem", { name: "Checking" });
    expect(checking).toHaveTextContent("closed Sep 15, 2026");
    expect(checking).toHaveTextContent("No gaps");
    expect(checking.querySelector("details")?.open).toBe(false);
    expect(within(checking).getByRole("link", { name: "Not read yet" })).toHaveAttribute("href", "/import");
    expect(screen.getByRole("heading", { name: "Coverage by month" })).toBeInTheDocument();
  });

  it("finds the gaps that need a download", () => {
    expect(missingGaps(TIMELINE[0]).map((g) => g.start)).toEqual(["2026-06-04"]);
    expect(downloadText({ closes: [] })).toBe("No statement: upload it");
    expect(downloadText({ closes: ["2026-06-03", "2026-07-03"] })).toBe(
      "Download the statements closing Jun 3, 2026 and Jul 3, 2026",
    );
  });
});

describe("Where each account stands", () => {
  it("says how each account's data arrives and what's next", () => {
    render(
      <MemoryRouter>
        <Arrivals
          sources={[
            {
              account_id: 1,
              name: "Diners Club Hernan",
              how: "email",
              last_day: "2026-10-03",
              state: "late",
              note: "Closed Nov 3 and hasn't arrived: check the Gmail script, or upload it on Import",
            },
            {
              account_id: 2,
              name: "BofA Adv Plus Banking",
              how: "bank_sync",
              last_day: "2026-11-11",
              state: "up_to_date",
              note: "Nothing to do",
            },
          ]}
        />
      </MemoryRouter>,
    );
    const late = screen.getByText("Diners Club Hernan").closest("tr")!;
    expect(within(late).getByText("Late")).toBeInTheDocument();
    expect(within(late).getByText("Email, by the Gmail script")).toBeInTheDocument();
    expect(within(late).getByRole("link", { name: /check the Gmail script/ })).toHaveAttribute(
      "href",
      "/import",
    );
    const bofa = screen.getByText("BofA Adv Plus Banking").closest("tr")!;
    expect(within(bofa).getByText("Bank sync, daily")).toBeInTheDocument();
    expect(within(bofa).getByText("Up to date")).toBeInTheDocument();
  });
});
