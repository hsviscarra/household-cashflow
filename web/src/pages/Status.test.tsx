import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DataStatus, MonthStatus } from "../api";
import StatusPage, { summary } from "./Status";

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
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status }))),
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
