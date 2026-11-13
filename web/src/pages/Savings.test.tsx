import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Savings } from "../api";
import { safeLine } from "../components/SafeToSpend";
import SavingsPage, { howLong, payoffLine, rateHeadline } from "./Savings";

const plan = (months: number | null, interest: string, order: string[]) => ({
  months,
  interest,
  order,
  paid_in: Object.fromEntries(order.map((k, i) => [k, (i + 1) * 9])),
});
const S: Savings = {
  today: "2026-10-20",
  months: [
    {
      month: "2026-09-01",
      money_in: "3000",
      spent: "1000",
      set_aside: "500",
      kept: "2000",
      rate: "0.6667",
      running: false,
    },
    {
      month: "2026-10-01",
      money_in: "3000",
      spent: "400",
      set_aside: "200",
      kept: "2600",
      rate: "0.8667",
      running: true,
    },
  ],
  rate_12: "0.6667",
  goals: {
    needed: "300",
    planned: "250",
    saved: "200",
    to_go: "50",
    short: "50",
    goals: [
      {
        goal_id: 1,
        name: "Trip",
        target_date: "2027-01-31",
        left: "1200",
        needed_monthly: "300",
        monthly_amount: "250",
        status: "behind",
      },
    ],
  },
  safe: {
    month: "2026-10-01",
    left_so_far: "2400",
    income_to_come: "0",
    bills_to_come: "1000",
    goals_to_go: "50",
    days_left: 12,
    amount: "1350",
    a_day: "112.50",
  },
  debts: [
    {
      key: "holding-1",
      name: "Car loan",
      kind: "loan",
      balance: "5000",
      as_of: "2026-10-01",
      rate: "0.2400",
      minimum: "150",
      rate_from: "typed",
      minimum_from: "typed",
      interest_12: "0",
      planned: true,
    },
    {
      key: "account-3",
      name: "Visa",
      kind: "card",
      balance: "2000",
      as_of: "2026-09-30",
      rate: null,
      minimum: null,
      rate_from: null,
      minimum_from: null,
      interest_12: "55.17",
      planned: false,
    },
  ],
  payoff: {
    extra: "200",
    minimums: plan(48, "2400.00", ["holding-1"]),
    avalanche: plan(17, "900.00", ["holding-1"]),
    snowball: plan(18, "1000.00", ["holding-1"]),
    saved: "100.00",
  },
};

let calls: { method: string; url: string; body: unknown }[];
let settings: Record<string, unknown>;
beforeEach(() => {
  calls = [];
  settings = {};
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      const json = (d: unknown) => Promise.resolve(new Response(JSON.stringify(d)));
      if (url.startsWith("/api/me/settings")) {
        if (method === "PUT") settings[decodeURIComponent(url.split("/").pop()!)] = body.value;
        return json({ user: "h", settings });
      }
      calls.push({ method, url, body });
      if (method === "PUT") return Promise.resolve(new Response(null, { status: 204 }));
      return json(S);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <SavingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Saving", () => {
  it("says the rate, how long a payoff takes, what is safe and what the orders cost", () => {
    expect(rateHeadline(S)).toBe("You kept 67% of what came in over the last 1 month");
    expect(rateHeadline({ ...S, rate_12: null })).toBe("Saving");
    expect(howLong(17, "2026-10-20")).toBe("17 months (February 2028)");
    expect(howLong(1, "2026-10-20")).toBe("1 month (October 2026)");
    expect(howLong(null, "2026-10-20")).toBe("never, at these payments");
    expect(howLong(0, "2026-10-20")).toBe("nothing to pay");
    expect(safeLine(S.safe)).toBe("1,350.00 until the end of the month, about 112.50 a day for 12 days.");
    expect(safeLine({ ...S.safe, amount: "-80", a_day: "0" })).toBe(
      "Nothing: the bills still due and your goals take 80.00 more than what is left.",
    );
    expect(payoffLine(S.payoff!, 200)).toBe(
      "With the monthly payments plus 200.00, and each paid-off debt's payment moved to the next, highest rate first costs 1,500.00 less interest than paying only the minimums. Highest rate first costs 100.00 less than smallest balance first.",
    );
    expect(payoffLine({ ...S.payoff!, saved: "0" }, 0)).toMatch(/Both orders cost the same here\.$/);
    expect(payoffLine({ ...S.payoff!, avalanche: plan(null, "9", []) }, 0)).toMatch(
      /never paid off: the payments don't cover the interest\.$/,
    );
  });

  it("shows the rate, the goals, the debts and the comparison, and saves what is typed", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", { level: 1, name: /^You kept 67% of what came in/ }),
    ).toBeInTheDocument();
    expect(calls[0].url).toBe("/api/savings");
    expect(screen.getByLabelText("Safe to spend")).toHaveTextContent("1,350.00");
    expect(screen.getByRole("img", { name: /^Share of income kept, by month/ })).toBeInTheDocument();
    const rates = screen.getByRole("table", { name: "Savings rate by month" });
    expect(within(rates).getAllByRole("row")[2]).toHaveTextContent(
      "October 2026 (so far)3,000.00400.002,600.0087%200.00",
    );

    expect(screen.getByLabelText("Goals this month")).toHaveTextContent(
      "your goals need 300.00 a month; you plan 250.00, 50.00 short. This month 200.00 went into savings so far; 50.00 of the plan is still to go.",
    );
    const goals = screen.getByRole("table", { name: "What each goal needs a month" });
    expect(within(goals).getAllByRole("row")[1]).toHaveTextContent(
      "TripJanuary 20271,200.00300.00250.00Behind",
    );

    const owed = screen.getByRole("table", { name: "What is owed" });
    expect(within(owed).getAllByRole("row")[1]).toHaveTextContent("Car loan5,000.0024.0%typed150.00typed—");
    // A card isn't a debt to plan until its rate is typed (it may just be this month's purchases).
    expect(within(owed).getAllByRole("row")[2]).toHaveTextContent(
      "Visa2,000.00type it if you carry a balance—55.17",
    );
    expect(screen.getByText(/^Cards are left out/)).toBeInTheDocument();
    expect(screen.queryByText(/Not in the comparison until its rate/)).not.toBeInTheDocument();
    const orders = screen.getByRole("table", { name: "Payoff orders compared" });
    expect(within(orders).getAllByRole("row")[2]).toHaveTextContent(
      "Highest rate first17 months (February 2028)900.00Car loan (9)",
    );
    expect(screen.getByLabelText("Payoff summary")).toHaveTextContent("1,500.00 less interest");

    // Typing the card's rate (a percent) and payment saves them as a fraction and an amount.
    fireEvent.click(within(owed).getByRole("button", { name: "Edit Visa" }));
    const form = screen.getByRole("form", { name: "Terms of Visa" });
    fireEvent.change(within(form).getByLabelText("Rate a year, %"), { target: { value: "15.6" } });
    fireEvent.change(within(form).getByLabelText("Paid a month"), { target: { value: "80" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(calls.find((c) => c.method === "PUT")).toEqual({
      method: "PUT",
      url: "/api/savings/debts/account-3",
      body: { rate: "0.1560", minimum: "80.00" },
    });

    // The extra is kept for the person and asked for.
    fireEvent.change(screen.getByLabelText("Extra toward debts each month"), { target: { value: "200" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    await waitFor(() => expect(calls.at(-1)!.url).toBe("/api/savings?extra=200"));
    expect(settings["savings:extra"]).toBe(200);
  });
});
