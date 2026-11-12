import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Bill, Bills } from "../api";
import BillsPage, { repeats, weeks } from "./Bills";

const bill = (p: Partial<Bill>): Bill => ({
  template_id: 1,
  entry_id: null,
  name: "BIESS",
  type: "debt_payment",
  group: "Housing",
  group_color: null,
  category_path: "Housing / Mortgage",
  account_name: "Produbanco Hernan",
  every_months: 1,
  due_day: 7,
  due_day_set: true,
  expected: "-505.19",
  paid: null,
  lines: 0,
  status: "due",
  avg3: "-505.19",
  payments_left: null,
  price_from: null,
  price_changed: null,
  end_month: null,
  ...p,
});
const BILLS: Bills = {
  month: "2026-11-01",
  today: "2026-11-06",
  bills: [
    bill({}),
    bill({
      template_id: 2,
      entry_id: 52,
      name: "Ecuasanitas",
      group: "Insurance",
      due_day: 1,
      expected: "-172.71",
      status: "late",
      avg3: null,
    }),
    bill({
      template_id: 3,
      name: "Anthropic",
      group: "Subscriptions",
      due_day: 5,
      expected: "-20",
      paid: "-20",
      lines: 1,
      status: "paid",
      price_from: "-18",
      price_changed: "2026-09-01",
    }),
    bill({
      template_id: 4,
      name: "New house",
      group: "Housing",
      due_day: 30,
      expected: "-3075.36",
      payments_left: 16,
      end_month: "2028-02-01",
    }),
    bill({
      template_id: 5,
      name: "Salary Lauren",
      type: "income",
      group: "Salary",
      due_day: 30,
      expected: "5382",
    }),
    bill({
      template_id: 6,
      name: "Car tax",
      group: "Transport",
      due_day: null,
      every_months: 0,
      expected: "-300",
    }),
  ],
};

let urls: string[];
let sent: { url: string; body: unknown }[];

beforeEach(() => {
  urls = [];
  sent = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      urls.push(url);
      if (init?.body) sent.push({ url, body: JSON.parse(String(init.body)) });
      const json = (d: unknown) => Promise.resolve(new Response(JSON.stringify(d)));
      if (url.startsWith("/api/recurring/bills")) return json(BILLS);
      if (url === "/api/subscriptions")
        return json({
          monthly_cost: "100",
          subscriptions: [
            {
              merchant: "MICROSOFT",
              cadence: "monthly",
              typical: "100",
              monthly_cost: "100",
              yearly_cost: "1200",
              category_path: null,
              accounts: ["Capital One"],
              charges: [],
              last: "2026-10-06",
              next_expected: "2026-11-06",
              active: true,
            },
          ],
        });
      if (url === "/api/accounts") return json([]);
      if (url === "/api/categories") return json([]);
      if (url.startsWith("/api/recurring/grid"))
        return json({ year: 2026, months: [], rows: [], excel_months: [] });
      if (url === "/api/recurring/templates") return json([]);
      return json([]);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderAt(path = "/recurring?month=2026-11") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <BillsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("bills helpers", () => {
  it("lays out a month Monday first and says how often", () => {
    const w = weeks("2026-11");
    expect(w[0]).toEqual([null, null, null, null, null, null, 1]); // Nov 1 2026 is a Sunday
    expect(w.at(-1)).toEqual([30, null, null, null, null, null, null]);
    expect(repeats(bill({}))).toBe("Monthly · 7th");
    expect(repeats(bill({ due_day: 1, every_months: 12 }))).toBe("Yearly · 1st");
    expect(repeats(bill({ due_day: 22, payments_left: 16 }))).toBe("Monthly · 22nd · 16 left");
    expect(repeats(bill({ due_day: 13, every_months: 0 }))).toBe("Once · 13th");
    expect(repeats(bill({ due_day: null, every_months: 5 }))).toBe("Every 5 months");
  });
});

describe("Bills & subscriptions", () => {
  it("shows the month's tiles and calendar with paid, due and late", async () => {
    renderAt();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Bills & subscriptions · November 2026" }),
    ).toBeTruthy();
    expect(urls).toContain("/api/recurring/bills?month=2026-11-01");
    expect(await screen.findByText("4,073.26")).toBeInTheDocument(); // committed: out, not income
    expect(screen.getByText("1 of 5")).toBeInTheDocument();
    expect(screen.getByText("Ecuasanitas", { selector: "dd *, dd" })).toBeInTheDocument();
    expect(await screen.findByText("1,200.00")).toBeInTheDocument(); // subscriptions a year
    // This month, by what needs attention first (ADR-052).
    const late = screen.getByRole("region", { name: "Late" });
    expect(late).toHaveTextContent("Ecuasanitas");
    expect(screen.getByRole("region", { name: "Paid" })).toHaveTextContent("Anthropic");
    expect(screen.getByRole("region", { name: "Paid" })).toHaveTextContent("was 18.00 until Sep");
    expect(screen.getByRole("region", { name: "Money coming in" })).toHaveTextContent("Salary Lauren");
    const prices = screen.getByRole("region", { name: /Price changes/ });
    expect(prices).toHaveTextContent("18.00 → 20.00 (+11%)");
    fireEvent.click(screen.getByRole("button", { name: "Calendar" }));
    const cal = await screen.findByRole("table", { name: "Bills by day" });
    const cells = within(cal).getAllByRole("cell");
    const day = (n: number) => cells.find((c) => c.querySelector("span")?.textContent === String(n))!;
    expect(day(1)).toHaveTextContent("Ecuasanitas 172.71, late");
    expect(day(5)).toHaveTextContent("Anthropic 20.00, paid");
    expect(day(30)).toHaveTextContent("New house");
    expect(day(30)).toHaveTextContent("↑ Salary Lauren 5,382.00, money in");
    expect(screen.getByText("No set day yet")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Oct →|← Oct/ }));
    expect(urls).toContain("/api/recurring/bills?month=2026-10-01");
  });

  it("changes a bill where it's listed: its day, skip, or stop it", async () => {
    renderAt();
    const late = await screen.findByRole("region", { name: "Late" });
    fireEvent.click(within(late).getByRole("button", { name: "Change Ecuasanitas" }));
    fireEvent.change(within(late).getByLabelText("Day Ecuasanitas is due"), { target: { value: "20" } });
    fireEvent.click(within(late).getByRole("button", { name: "Save day" }));
    await vi.waitFor(() => expect(sent.some((c) => c.url === "/api/recurring/templates/2")).toBe(true));
    expect(sent.find((c) => c.url === "/api/recurring/templates/2")!.body).toEqual({ due_day: 20 });

    fireEvent.click(within(late).getByRole("button", { name: "Change Ecuasanitas" }));
    fireEvent.click(within(late).getByRole("button", { name: "Skip this month" }));
    await vi.waitFor(() => expect(sent.some((c) => c.url === "/api/recurring/entries/52")).toBe(true));
    expect(sent.find((c) => c.url === "/api/recurring/entries/52")!.body).toEqual({ status: "skipped" });

    fireEvent.click(within(late).getByRole("button", { name: "Change Ecuasanitas" }));
    fireEvent.click(within(late).getByRole("button", { name: "Doesn't apply any more" }));
    expect(late).toHaveTextContent("Ends before November 2026; what was paid stays.");
    fireEvent.click(within(late).getByRole("button", { name: "Yes, stop it" }));
    await vi.waitFor(() => expect(sent.some((c) => c.url === "/api/recurring/templates/2/stop")).toBe(true));
    expect(sent.find((c) => c.url === "/api/recurring/templates/2/stop")!.body).toEqual({
      month: "2026-11-01",
    });
  });

  it("groups items with totals", async () => {
    renderAt("/recurring?month=2026-11&view=group");
    const table = await screen.findByRole("table");
    const housing = within(table).getByRole("button", { name: /Housing/ });
    expect(housing).toHaveAttribute("aria-expanded", "true");
    expect(within(table).getByText("Monthly · 30th · 16 left")).toBeInTheDocument();
    const subs = within(table).getByRole("button", { name: /Subscriptions/ });
    fireEvent.click(subs);
    expect(within(table).getByText("Anthropic")).toBeInTheDocument();
    expect(within(table).getByText("1 price change")).toBeInTheDocument();
    fireEvent.click(housing);
    expect(within(table).queryByText("New house")).not.toBeInTheDocument();
  });

  it("opens the year grid, the subscriptions found and the form to add a bill", async () => {
    renderAt("/recurring?month=2026-11&view=grid");
    expect(await screen.findByRole("heading", { level: 2, name: "Recurring" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Subscriptions" }));
    expect(await screen.findByRole("heading", { level: 2, name: /subscriptions/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add a bill" }));
    const form = await screen.findByRole("form", { name: "New template" });
    expect(within(form).getByLabelText("Repeats")).toHaveValue("1");
    expect(within(form).getByRole("option", { name: "Once" })).toBeInTheDocument();
    expect(within(form).getByLabelText("On day (optional)")).toBeInTheDocument();
    expect(within(form).getByLabelText("Last month (optional)")).toBeInTheDocument();
  });

  it("says when nothing repeats", async () => {
    vi.mocked(fetch).mockImplementation((url) =>
      Promise.resolve(
        new Response(
          JSON.stringify(String(url).startsWith("/api/recurring/bills") ? { ...BILLS, bills: [] } : []),
        ),
      ),
    );
    renderAt();
    expect(await screen.findByText(/Nothing repeats in November 2026 yet/)).toBeInTheDocument();
  });
});
