import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SpendSeries } from "../api";
import SpendingChart, { choice, monthsOf, toCsv } from "./SpendingChart";

const WHOLE: SpendSeries = {
  months: ["2026-09-01", "2026-10-01"],
  by: "none",
  series: [{ key: "Spending", label: "Spending", color: null, values: ["300.00", "500.00"] }],
};
const GROUPS: SpendSeries = {
  months: ["2026-09-01", "2026-10-01"],
  by: "group",
  series: [
    { key: "Groceries", label: "Groceries", color: "#4E9A2A", values: ["200.00", "350.00"] },
    { key: "Dining", label: "Dining, out", color: "#E2583E", values: ["100.00", "150.00"] },
  ],
};

let urls: string[];
beforeEach(() => {
  urls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      urls.push(url);
      const body = url.includes("by=group") ? GROUPS : WHOLE;
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderChart() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["settings"], { user: "t", settings: {} });
  render(
    <QueryClientProvider client={client}>
      <SpendingChart month="2026-10-01" person="Hernan" />
    </QueryClientProvider>,
  );
}

describe("SpendingChart", () => {
  it("reads a saved choice, counts the months of a period and writes the CSV", () => {
    expect(choice({ period: "6", by: "person", show: "share" })).toEqual({
      period: "6",
      by: "person",
      show: "share",
    });
    expect(choice({ period: "99", by: "x" })).toEqual({ period: "12", by: "none", show: "amounts" });
    expect(monthsOf("ytd", "2026-10-01")).toBe(10);
    expect(monthsOf("24", "2026-10-01")).toBe(24);
    expect(toCsv(WHOLE)).toBe("Month,Spending\n2026-09,300.00\n2026-10,500.00");
    expect(toCsv(GROUPS)).toBe(
      'Month,Groceries,"Dining, out",Total\n2026-09,200.00,100.00,300.00\n2026-10,350.00,150.00,500.00',
    );
  });

  it("asks for the period and the split that were chosen, and shows the numbers as a table", async () => {
    renderChart();
    expect(
      await screen.findByRole("img", { name: /^Spending by month, September 2026 to October 2026/ }),
    ).toBeInTheDocument();
    expect(urls[0]).toBe("/api/spending/series?month=2026-10-01&months=12&by=none&person=Hernan");

    fireEvent.change(screen.getByLabelText("Split by"), { target: { value: "group" } });
    expect(await screen.findByRole("img", { name: /by group/ })).toBeInTheDocument();
    expect(urls.at(-1)).toContain("by=group");
    const table = screen.getByRole("table", { name: /by group/ });
    expect(within(table).getAllByRole("row").at(-1)).toHaveTextContent("October 2026350.00150.00500.00");

    fireEvent.change(screen.getByLabelText("Period"), { target: { value: "ytd" } });
    await vi.waitFor(() => expect(urls.at(-1)).toContain("months=10"));
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "share" } });
    expect(await screen.findByRole("img", { name: /as a share of each month/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "table" } });
    await vi.waitFor(() => expect(screen.queryByRole("img")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Download CSV" })).toBeInTheDocument();
  });
});
