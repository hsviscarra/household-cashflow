import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PersonTax } from "../api";
import TaxProjectionPage from "./TaxProjection";

const base = {
  year: 2026,
  typical_month: "3000.00",
  expenses: "0.00",
  cap: "5752.60",
  pay_on: "2027-03-15",
  months_left: 4,
};
const HERNAN: PersonTax = {
  ...base,
  person: "Hernan",
  profile: { regime: "foreign", withheld: "0", exempt: "0", deductions: "0" },
  received: "30000.00",
  projected_income: "36000.00",
  taxable: "36000.00",
  tax: "2850.80",
  rebate: "0.00",
  room: "5752.60",
  more_rebate: "1035.47",
  due: "2850.80",
  to_pay: "2850.80",
  set_aside: "712.70",
  notes: ["Nothing is withheld on this income: all of it is paid with the return."],
};
const LAUREN: PersonTax = {
  ...base,
  person: "Lauren",
  profile: { regime: "employee", withheld: "300", exempt: "1900", deductions: "0" },
  received: "15000.00",
  projected_income: "18000.00",
  taxable: "16400.00",
  tax: "252.10",
  rebate: "0.00",
  room: "0.00",
  more_rebate: "0.00",
  due: "252.10",
  to_pay: "-47.90",
  set_aside: "0.00",
  notes: [],
};

let calls: { method: string; url: string; body: unknown }[];
beforeEach(() => {
  calls = [];
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-12T12:00:00"));
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      calls.push({
        method: init?.method ?? "GET",
        url,
        body: init?.body ? JSON.parse(String(init.body)) : null,
      });
      const data = init?.method === "PUT" ? LAUREN : [HERNAN, LAUREN];
      return Promise.resolve(new Response(JSON.stringify(data), { status: 200 }));
    }),
  );
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Income tax", () => {
  it("shows what each owes, the room left in deductions and saves the profile", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <TaxProjectionPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const h = await screen.findByRole("region", { name: "Hernan's income tax" });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Income tax 2026");
    expect(h).toHaveTextContent("To pay with the return2,850.80");
    expect(h).toHaveTextContent(
      "Due around March 15, 2027. Setting aside 712.70 a month for 4 months covers it.",
    );
    expect(h).toHaveTextContent("5,752.60 more in deductible invoices before December 31 would still count");
    expect(h).toHaveTextContent("taking up to 1,035.47 off the tax");
    expect(h).toHaveTextContent("Nothing is withheld on this income");

    const l = screen.getByRole("region", { name: "Lauren's income tax" });
    expect(l).toHaveTextContent("In your favour47.90");
    expect(l).toHaveTextContent("Nothing to set aside");
    fireEvent.change(within(l).getByLabelText(/Withheld in the year/), { target: { value: "350" } });
    fireEvent.click(within(l).getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.url).toBe("/api/taxes/2026/projection/Lauren");
    expect(put.body).toEqual({ regime: "employee", withheld: "350", exempt: "1900", deductions: "0" });
  });
});
