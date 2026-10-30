import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Portfolio } from "../api";
import InvestmentsSection, { portfolioLine } from "./Investments";

const P: Portfolio = {
  holding_id: 7,
  as_of: "2026-10-28",
  total: "25350.40",
  cash: "350.40",
  previous_total: "24400",
  previous_as_of: "2026-10-27",
  stale: false,
  positions: [
    {
      symbol: "VT",
      description: "VANGUARD TOT WORLD STK ETF",
      asset_class: "STK",
      currency: "USD",
      quantity: "150",
      price: "120.5",
      value: "18075",
      cost_basis: "15000",
      unrealized: "3075",
    },
    {
      symbol: "IWDA",
      description: null,
      asset_class: "STK",
      currency: "EUR",
      quantity: "80.1234",
      price: "80",
      value: "6912",
      cost_basis: null,
      unrealized: null,
    },
  ],
};
const EMPTY: Portfolio = {
  ...P,
  holding_id: null,
  as_of: null,
  total: null,
  cash: null,
  previous_total: null,
  previous_as_of: null,
  positions: [],
};

function renderWith(get: Portfolio | Response, post?: Response) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if ((init?.method ?? "GET") === "POST")
        return Promise.resolve(
          post ??
            new Response(
              JSON.stringify({ holding_id: 7, as_of: "2026-10-29", total: "1", cash: "0", positions: 1 }),
            ),
        );
      return Promise.resolve(get instanceof Response ? get : new Response(JSON.stringify(get)));
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <InvestmentsSection />
    </QueryClientProvider>,
  );
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

describe("investments", () => {
  it("summarizes the portfolio", () => {
    expect(portfolioLine(P)).toBe("25,350.40 on Oct 28, 2026 (+950.40 since Oct 27, 2026)");
    expect(portfolioLine({ ...P, previous_total: null })).toBe("25,350.40 on Oct 28, 2026");
    expect(portfolioLine(EMPTY)).toBeNull();
  });

  it("shows the positions, and no hint while it is recent", async () => {
    const calls = renderWith(P);
    const section = await screen.findByRole("region", { name: "Investments" });
    expect(within(section).getByText("Total").nextSibling).toHaveTextContent("25,350.40");
    expect(within(section).getByText("Unrealized gain").nextSibling).toHaveTextContent("+3,075.00");
    const rows = within(section).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("VTVANGUARD TOT WORLD STK ETF150120.5018,075.00+3,075.0071%");
    expect(rows[2]).toHaveTextContent("IWDA80.123480.00 EUR6,912.00—27%");
    expect(section).not.toHaveTextContent("ask Claude");
    expect(calls.filter((c) => c.startsWith("POST"))).toHaveLength(0);
  });

  it("a week old: suggests asking Claude", async () => {
    renderWith({ ...P, stale: true });
    const section = await screen.findByRole("region", { name: "Investments" });
    expect(section).toHaveTextContent("This is more than a week old. To update it, ask Claude:");
    expect(section).toHaveTextContent("Update my IBKR portfolio in the cash flow app.");
  });

  it("nothing saved yet: explains, and takes an uploaded report; shows errors", async () => {
    const calls = renderWith(
      EMPTY,
      new Response(JSON.stringify({ detail: "This isn't a Flex report (XML)." }), { status: 422 }),
    );
    const section = await screen.findByRole("region", { name: "Investments" });
    expect(section).toHaveTextContent("No portfolio saved yet.");
    expect(section).toHaveTextContent("To update it, ask Claude:");
    expect(section).not.toHaveTextContent("more than a week old");
    fireEvent.change(within(section).getByLabelText("Flex report"), {
      target: { files: [new File(["<x/>"], "f.xml", { type: "text/xml" })] },
    });
    expect(await within(section).findByText("This isn't a Flex report (XML).")).toBeInTheDocument();
    expect(calls).toContain("POST /api/investments/ibkr/upload");
  });

  it("on a load error", async () => {
    renderWith(new Response("{}", { status: 500 }));
    expect(await screen.findByText("Could not load the investments.")).toBeInTheDocument();
  });
});
