import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_AHEAD, type Ahead, type AheadYear } from "../api";
import NetWorthAheadPage, { aheadHeadline, choices, milestonesOf } from "./NetWorthAhead";

const year = (y: number, net: string, more: Partial<AheadYear> = {}): AheadYear => ({
  year: y,
  end: `${y}-12-31`,
  cash: "2000",
  investments_low: "10000",
  investments: "10500",
  investments_high: "11000",
  property: "100000",
  vehicles: "0",
  other_assets: "0",
  loans: "600",
  other_debts: "0",
  kept: "24000",
  net_low: String(Number(net) - 500),
  net,
  net_high: String(Number(net) + 500),
  milestones: [],
  ...more,
});
const A: Ahead = {
  today: "2026-10-20",
  kept_a_year: "24000",
  net_today: "107400",
  loans: [
    { name: "Mortgage", balance: "2000", from_table: true, paid_off: "2026-12-01" },
    { name: "Family loan", balance: "600", from_table: false, paid_off: null },
  ],
  years: [
    year(2026, "111900", { milestones: ["Mortgage paid off"] }),
    year(2027, "136400"),
    year(2028, "161000"),
  ],
};

let urls: string[];
let settings: Record<string, unknown>;
beforeEach(() => {
  urls = [];
  settings = {};
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const json = (d: unknown) => Promise.resolve(new Response(JSON.stringify(d)));
      if (url.startsWith("/api/me/settings")) {
        if (init?.method === "PUT")
          settings[decodeURIComponent(url.split("/").pop()!)] = JSON.parse(String(init.body)).value;
        return json({ user: "h", settings });
      }
      urls.push(url);
      return json(A);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <NetWorthAheadPage />
    </QueryClientProvider>,
  );
}

describe("Net worth, years ahead", () => {
  it("reads saved choices and milestones, and says where net worth ends", () => {
    expect(choices(undefined)).toEqual(DEFAULT_AHEAD);
    // Returns are put in order; rates out of range are pulled in; a share stays a share.
    expect(
      choices({ years: 10, low: 0.09, expected: 0.04, high: 0.06, invest_share: 3, property_growth: "x" }),
    ).toEqual({
      ...DEFAULT_AHEAD,
      years: 10,
      low: 0.04,
      expected: 0.06,
      high: 0.09,
      invest_share: 1,
    });
    expect(milestonesOf([{ name: "School", date: "2029-09-01" }, { name: "Bad", date: "soon" }, 4])).toEqual([
      { name: "School", date: "2029-09-01" },
    ]);
    expect(aheadHeadline(A)).toBe(
      "In 2028 your net worth is about 161,000.00 (between 160,500.00 and 161,500.00), 53,600.00 more than today",
    );
    expect(aheadHeadline({ ...A, years: [] })).toBe("Years ahead");
  });

  it("shows the years, asks again when a choice changes and keeps your milestones", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", { level: 1, name: /^In 2028 your net worth is about/ }),
    ).toBeInTheDocument();
    expect(urls[0]).toBe(
      "/api/networth/ahead?years=5&low=0.02&expected=0.05&high=0.08&property_growth=0&vehicle_growth=-0.1&invest_share=0",
    );
    expect(screen.getByLabelText("What it starts from")).toHaveTextContent(
      "no interest is counted for: Family loan.",
    );
    expect(
      screen.getByRole("img", { name: /^What you own by year, and net worth as a line, 2026 to 2028/ }),
    ).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Net worth by year" });
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent(
      "202624,000.002,000.0010,500.00100,000.00600.00111,900.00111,400.00 to 112,400.00Mortgage paid off",
    );

    fireEvent.click(screen.getByRole("button", { name: "10 years" }));
    await waitFor(() => expect(urls.at(-1)).toContain("years=10"));
    const expected = screen.getByLabelText("Return, expected %");
    fireEvent.change(expected, { target: { value: "6.5" } });
    fireEvent.blur(expected);
    await waitFor(() => expect(urls.at(-1)).toContain("expected=0.065"));
    expect(settings["long-view"]).toMatchObject({ years: 10, expected: 0.065 });

    fireEvent.change(screen.getByLabelText("Milestone"), { target: { value: "High school starts" } });
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2027-09-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Add milestone" }));
    await waitFor(() =>
      expect(settings["long-view:milestones"]).toEqual([{ name: "High school starts", date: "2027-09-01" }]),
    );
    expect(within(table).getAllByRole("row")[2]).toHaveTextContent("High school starts");
    fireEvent.click(screen.getByRole("button", { name: "Remove High school starts" }));
    await waitFor(() => expect(settings["long-view:milestones"]).toEqual([]));
  });
});
