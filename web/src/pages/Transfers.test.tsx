import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import TransfersPage from "./Transfers";

const WB = {
  places: ["Lauren's flexible savings", "Wise"],
  bunches: [
    {
      key: "TRANSFERENCIA|2000",
      description: "TRANSFERENCIA CTAS TERCEROS BCA ENL",
      amount: "2000.00",
      lines: [
        {
          transaction_id: 11,
          txn_date: "2026-08-04",
          amount: "2000.00",
          description: "TRANSFERENCIA CTAS TERCEROS BCA ENL",
          account_name: "Produbanco Lauren",
          category_id: null,
          statement_file_id: 3,
          candidates: [],
        },
        {
          transaction_id: 10,
          txn_date: "2026-08-01",
          amount: "2000.00",
          description: "TRANSFERENCIA CTAS TERCEROS BCA ENL",
          account_name: "Produbanco Lauren",
          category_id: null,
          statement_file_id: 3,
          candidates: [
            {
              transaction_id: 5,
              txn_date: "2026-08-02",
              amount: "-2000.00",
              description: "PAGO",
              account_name: "Banco Pichincha",
              days: 1,
            },
          ],
        },
      ],
    },
  ],
};

afterEach(() => vi.unstubAllGlobals());

describe("Transfers to settle (ADR-075)", () => {
  it("pairs a line and settles the rest where the app doesn't look", async () => {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        calls.push([url, init]);
        const body =
          url === "/api/transfers/workbench"
            ? WB
            : url === "/api/people"
              ? []
              : url === "/api/categories"
                ? []
                : { settled: 2, group: 5 };
        return Promise.resolve(new Response(JSON.stringify(body)));
      }),
    );
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <TransfersPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      await screen.findByRole("heading", { level: 1, name: "2 transfers to settle" }),
    ).toBeInTheDocument();
    const card = screen.getByRole("region", { name: /TRANSFERENCIA CTAS TERCEROS BCA ENL/ });
    fireEvent.click(within(card).getByRole("button", { name: /Pair with Banco Pichincha/ }));
    await waitFor(() => expect(calls.some(([u]) => u === "/api/transfers/pair")).toBe(true));
    const pairBody = JSON.parse(String(calls.find(([u]) => u === "/api/transfers/pair")![1]!.body));
    expect(pairBody).toEqual({ a: 10, b: 5 });
    fireEvent.change(within(card).getByLabelText("The other side is"), { target: { value: "Wise" } });
    fireEvent.click(within(card).getByRole("button", { name: "Settle" }));
    await waitFor(() => expect(calls.some(([u]) => u === "/api/transfers/outside")).toBe(true));
    const body = JSON.parse(String(calls.find(([u]) => u === "/api/transfers/outside")![1]!.body));
    expect(body).toEqual({ ids: [11, 10], place: "Wise" });
  });
});
