import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Projection } from "../api";
import ProjectionsPage, { projectionHeadline } from "./Projections";

const month = (m: string, net: string, end: string) => ({
  month: m,
  income: "3000",
  fixed: "1200",
  variable: "300",
  purchases: "500",
  net,
  end_cash: end,
  items: [
    { day: `${m.slice(0, 8)}01`, name: "Rent", amount: "-1200", kind: "fixed" as const },
    { day: `${m.slice(0, 8)}15`, name: "Salary", amount: "3000", kind: "income" as const },
  ],
});
const P: Projection = {
  today: "2026-10-20",
  start_cash: "2000",
  cash_as_of: "2026-09-30",
  variable_per_month: "300",
  average_months: ["2026-07-01", "2026-08-01", "2026-09-01"],
  months: [
    month("2026-11-01", "1000", "2900"),
    month("2026-12-01", "1000", "3900"),
    month("2027-01-01", "-500", "3400"),
  ],
  daily: [
    { day: "2026-10-20", balance: "1990" },
    { day: "2026-11-01", balance: "-150" },
    { day: "2026-11-14", balance: "-250.5" },
    { day: "2026-11-15", balance: "2750" },
  ],
  lowest: { day: "2026-11-14", balance: "-250.5" },
  next_payday: { day: "2026-11-15", name: "Salary", amount: "3000", kind: "income" },
  alerts: [
    { month: "2026-09-01", group_id: 3, group_name: "Dining", amount: "200", average: "100", change: "1" },
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
        <ProjectionsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("Projections", () => {
  it("leads with the net and the lowest cash before payday", () => {
    expect(projectionHeadline(P)).toBe(
      "Next 3 months: +1,500.00; lowest cash −250.50 on Nov 14, before Salary on Nov 15.",
    );
    expect(projectionHeadline({ ...P, lowest: null, next_payday: null })).toBe("Next 3 months: +1,500.00.");
    expect(
      projectionHeadline({ ...P, lowest: { day: "2026-11-14", balance: "10" }, next_payday: null }),
    ).toBe("Next 3 months: +1,500.00; lowest cash 10.00 on Nov 14.");
  });

  it("shows the months, the warning, the daily cash and the alerts", async () => {
    renderWith(P);
    expect(
      await screen.findByRole("heading", { level: 1, name: /^Next 3 months: \+1,500.00/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Cash runs short: 250.50 below zero on Nov 14/)).toBeInTheDocument();
    expect(screen.getByText("Cash today").nextSibling).toHaveTextContent("2,000.00");
    expect(screen.getByText("bank statements to Sep 30")).toBeInTheDocument();
    expect(screen.getByText("Money in, 3 months").nextSibling).toHaveTextContent("9,000.00");
    expect(screen.getByText("Money out, 3 months").nextSibling).toHaveTextContent("6,000.00");
    expect(screen.getByText("Cash at the end of Jan").nextSibling).toHaveTextContent("3,400.00");
    const table = screen.getByRole("table", { name: "Projection for the next 3 months" });
    expect(within(table).getByRole("row", { name: /^Net/ })).toHaveTextContent("+1,000.00+1,000.00−500.00");
    expect(within(table).getByRole("row", { name: /^Cash at month end/ })).toHaveTextContent("2,900.00");
    expect(screen.getByText(/average of Jul, Aug, Sep/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("November 2026 · 2 items"));
    expect(screen.getByRole("list", { name: "Items in November 2026" })).toHaveTextContent(
      "Nov 15 · Salary+3,000.00",
    );
    expect(screen.getByRole("img", { name: "Projected cash from Oct 20 to Nov 15" })).toBeInTheDocument();
    const alerts = screen.getByRole("list", { name: "Spending alerts" });
    expect(alerts).toHaveTextContent("Dining: 200.00 in September 2026, 100% above its 100.00 average");
    expect(within(alerts).getByRole("link", { name: "See the spending" })).toHaveAttribute(
      "href",
      "/spending?month=2026-09",
    );
  });

  it("without alerts, statements or a shortfall, and on errors", async () => {
    const calm = {
      ...P,
      cash_as_of: null,
      average_months: [],
      lowest: { day: "2026-11-14", balance: "50" },
      alerts: [{ ...P.alerts[0], change: null }],
    };
    const { unmount } = renderWith(calm);
    expect(await screen.findByText("no bank statement yet")).toBeInTheDocument();
    expect(screen.queryByText(/Cash runs short/)).toBeNull();
    expect(screen.getByText(/average of no complete month yet/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Spending alerts" })).toHaveTextContent(
      "above its 100.00 average",
    );
    unmount();
    const second = renderWith({ ...P, alerts: [] });
    expect(
      await screen.findByText("No category is more than 30% above its recent average."),
    ).toBeInTheDocument();
    second.unmount();
    renderWith({ detail: "boom" }, 500);
    expect(await screen.findByText("Could not load the projection: boom")).toBeInTheDocument();
  });
});
