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

  it("warns per account, changes the horizon and floor, and runs what-ifs", async () => {
    const run = (id: number, name: string, low: string, short: string | null, move: string) => ({
      account_id: id,
      name,
      start: "1000",
      as_of: "2026-09-30",
      daily: P.daily,
      lowest: { day: "2026-11-14", balance: low },
      under_floor: short,
      move,
    });
    const F: Projection = {
      ...P,
      horizon: 3,
      average_over: 3,
      floor: "500",
      held: "1237.09",
      include_held: false,
      accounts: [run(1, "Pichincha", "-300", "2026-11-01", "800"), run(2, "Produbanco", "900", null, "0")],
      first_short: "2026-11-01",
      end_cash: "2750",
      base: null,
    };
    const calls: { method: string; url: string; body?: string }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        calls.push({ method, url, body: init?.body as string | undefined });
        const json = (b: unknown) => Promise.resolve(new Response(JSON.stringify(b)));
        if (url.startsWith("/api/me/settings")) return json({ user: "h", settings: {} });
        if (url === "/api/accounts")
          return json([
            { account_id: 1, name: "Pichincha", kind: "checking", is_active: true },
            { account_id: 2, name: "Produbanco", kind: "savings", is_active: true },
            { account_id: 3, name: "Visa", kind: "credit_card", is_active: true },
          ]);
        if (method === "POST")
          return json({
            ...F,
            end_cash: "2650",
            first_short: null,
            base: { lowest: F.lowest, first_short: "2026-11-01", end_cash: "2750" },
          });
        return json(F);
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <ProjectionsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const heads = await screen.findByRole("region", { name: "Heads-up" });
    expect(heads).toHaveTextContent(
      "Pichincha dips to −300.00 on Nov 14, under your 500.00 floor from Nov 1. Move 800.00 in before Nov 1.",
    );
    expect(heads).not.toHaveTextContent("Produbanco");
    expect(screen.getByRole("list", { name: "Lines" })).toHaveTextContent("Dashed red: your floor 500.00");
    expect(screen.getByText(/Money held for others/).closest("dt")).toHaveTextContent(
      "(1,237.09) counted as yours",
    );

    fireEvent.click(
      within(screen.getByRole("group", { name: "Horizon" })).getByRole("button", { name: "12 months" }),
    );
    await vi.waitFor(() => expect(calls.some((c) => c.url.includes("horizon=12"))).toBe(true));
    expect(calls.some((c) => c.method === "PUT" && c.url === "/api/me/settings/forecast")).toBe(true);

    fireEvent.change(screen.getByLabelText("Floor"), { target: { value: "750" } });
    fireEvent.click(screen.getByRole("button", { name: "Set" }));
    await vi.waitFor(() => expect(calls.some((c) => c.url.includes("floor=750"))).toBe(true));

    // Move money each month: one change out of the first account and one into the second.
    const form = screen.getByRole("form", { name: "Add a what-if" });
    await within(form).findAllByRole("option", { name: "Produbanco" });
    expect(within(form).queryAllByRole("option", { name: "Visa" })).toHaveLength(0);
    fireEvent.change(within(form).getByLabelText("Amount"), { target: { value: "200" } });
    fireEvent.change(within(form).getByLabelText("From"), { target: { value: "2" } });
    fireEvent.change(within(form).getByLabelText("To"), { target: { value: "1" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add to the forecast" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const sent = JSON.parse(calls.find((c) => c.method === "POST")!.body!);
    expect(sent.changes).toEqual([
      { name: "Move Produbanco → Pichincha", amount: "-200", every: "month", day: 1, account_id: 2 },
      { name: "Move Produbanco → Pichincha", amount: "200", every: "month", day: 1, account_id: 1 },
    ]);
    expect(await screen.findByText(/With these: lowest cash/)).toHaveTextContent(
      "first day short none (was Nov 1), cash at the end 2,650.00 (was 2,750.00).",
    );

    // A one-off coming in, then remove them all.
    fireEvent.click(screen.getByRole("button", { name: "A one-off" }));
    fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "Bonus" } });
    fireEvent.change(within(form).getByLabelText("Money"), { target: { value: "in" } });
    fireEvent.change(within(form).getByLabelText("Amount"), { target: { value: "500" } });
    fireEvent.change(within(form).getByLabelText("On"), { target: { value: "2026-12-10" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add to the forecast" }));
    const added = screen.getByRole("list", { name: "What-ifs added" });
    expect(added).toHaveTextContent("Bonus: +500.00 on Dec 10");
    for (let i = 0; i < 3; i++) fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[0]);
    expect(screen.queryByRole("list", { name: "What-ifs added" })).toBeNull();
  });
});
