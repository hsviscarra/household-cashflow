import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { GroupBudget, MonthBudget } from "../api";
import BudgetPage, { leftWords } from "./Budget";

const group = (over: Partial<GroupBudget>): GroupBudget => ({
  group_id: 1,
  name: "Groceries",
  color: "#16a34a",
  budget: "260",
  rollover: false,
  carried: "0",
  spent: "150",
  available: "260",
  left: "110",
  expected: "86.67",
  status: "ahead",
  suggested: "260",
  since: "2026-11-01",
  ...over,
});

const MONTH: MonthBudget = {
  month: "2026-11-01",
  day_share: "0.3333",
  groups: [
    group({}),
    group({
      group_id: 2,
      name: "Dining",
      budget: "200",
      available: "150",
      carried: "-50",
      spent: "20",
      left: "130",
      status: "on_track",
      rollover: true,
    }),
    group({
      group_id: 3,
      name: "Pets",
      budget: null,
      available: "0",
      spent: "40",
      left: "-40",
      status: "none",
      suggested: "50",
    }),
  ],
  budgeted: "410",
  spent: "170",
  unbudgeted: "40",
  left: "240",
  has_plans: true,
};

afterEach(() => vi.unstubAllGlobals());

function renderPage(body: MonthBudget, calls: { method: string; url: string; body?: string }[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body as string | undefined });
      if (method === "PUT") return Promise.resolve(new Response(null, { status: 204 }));
      if (method === "POST") return Promise.resolve(new Response(JSON.stringify({ added: 3 })));
      if (url.endsWith("/yearly-bills"))
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                template_id: 7,
                name: "Water",
                every_months: 3,
                amount: "90",
                monthly: "30",
                next_due: "2027-01-01",
                months_to_go: 3,
                should_have: "30",
              },
              {
                template_id: 8,
                name: "Car insurance",
                every_months: 12,
                amount: "1200",
                monthly: "100",
                next_due: "2027-03-01",
                months_to_go: 5,
                should_have: "800",
              },
            ]),
          ),
        );
      return Promise.resolve(new Response(JSON.stringify(body)));
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={["/budget?month=2026-11"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <BudgetPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Budget", () => {
  it("shows each group's pace and rollover, and changes a budget from this month on", async () => {
    const calls: { method: string; url: string; body?: string }[] = [];
    renderPage(MONTH, calls);
    expect(await screen.findByRole("heading", { name: "Budget, November 2026" })).toBeInTheDocument();
    const groceries = await screen.findByRole("region", { name: "Groceries" });
    expect(groceries).toHaveTextContent("Ahead of pace");
    expect(groceries).toHaveTextContent("150.00 of 260.00");
    expect(groceries).toHaveTextContent("110.00 left · 86.67 by today");
    expect(within(groceries).getByRole("img", { name: "58% of the budget spent" })).toBeInTheDocument();
    const dining = screen.getByRole("region", { name: "Dining" });
    expect(dining).toHaveTextContent("Rollover");
    expect(dining).toHaveTextContent("−50.00 from earlier months");
    const pets = screen.getByRole("region", { name: "Pets" });
    expect(pets).toHaveTextContent("40.00 spent · average 50.00 a month");

    fireEvent.click(within(pets).getByRole("button", { name: "Set a budget" }));
    fireEvent.click(within(pets).getByLabelText("Roll what's left into next month"));
    fireEvent.click(within(pets).getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.url).toBe("/api/budget/groups/3");
    expect(JSON.parse(put.body!)).toEqual({ from_month: "2026-11-01", amount: "50", rollover: true });

    const yearly = await screen.findByRole("table", { name: "Bills that come every few months" });
    expect(yearly).toHaveTextContent("Car insuranceyearly1,200.00100.00Mar 2027in 5 months800.00");
    expect(screen.getByText(/aside each month and these never catch you short/)).toHaveTextContent(
      "Put 130.00 aside each month and these never catch you short. By now about 830.00 should be set aside for them.",
    );

    fireEvent.click(screen.getByRole("button", { name: "Next month" }));
    await vi.waitFor(() => expect(calls.some((c) => c.url === "/api/budget/2026-12")).toBe(true));
  });

  it("offers the 3-month average when nothing is budgeted", async () => {
    const calls: { method: string; url: string }[] = [];
    renderPage({ ...MONTH, groups: [MONTH.groups[2]], has_plans: false }, calls);
    fireEvent.click(await screen.findByRole("button", { name: "Start from the 3-month average" }));
    await vi.waitFor(() =>
      expect(
        calls.some((c) => c.method === "POST" && c.url === "/api/budget/2026-11/start-from-average"),
      ).toBe(true),
    );
  });

  it("words what's left", () => {
    expect(leftWords(group({ left: "-40" }), 0.5)).toBe("40.00 over");
    expect(leftWords(group({}), 1)).toBe("110.00 left");
    expect(leftWords(group({ budget: null }), 0.5)).toBe("150.00 spent");
  });
});
