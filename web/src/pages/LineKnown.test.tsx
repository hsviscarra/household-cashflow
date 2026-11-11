import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LineContext, Txn } from "../api";
import { LineKnown } from "./Transactions";

const CTX: LineContext = {
  transaction_id: 7,
  category_source: null,
  rule: null,
  same_amount: [
    {
      transaction_id: 3,
      txn_date: "2026-09-22",
      amount: "-89.69",
      description: "TRANSFERENCIA INTERNET",
      account_name: "Banco Pichincha",
      category_path: "Housing / Office Alícuota",
      type: "expense",
    },
  ],
  transfer_side: [],
  transfer_candidates: [],
  invoices: [
    {
      invoice_id: 9,
      issuer_name: "CORPORACION FAVORITA",
      issue_date: "2026-10-21",
      total: "89.69",
      products: ["Leche"],
      linked: false,
    },
  ],
  purpose: {
    account_name: "Diners Club Lauren",
    for_whom: "Juliana",
    usual: ["EINSTEIN", "SKOLE"],
    unusual: true,
  },
};
const CATS = [
  {
    category_id: 1,
    name: "Housing",
    kind: "expense",
    children: [{ category_id: 42, name: "Office Alícuota", kind: "expense", children: [] }],
  },
];

afterEach(() => vi.unstubAllGlobals());

describe("What we know about a line (ADR-074)", () => {
  it("shows same-amount lines, invoices and the card's purpose, and acts on them", async () => {
    const calls: [string, RequestInit | undefined][] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        calls.push([url, init]);
        const body = url.endsWith("/context") ? CTX : url === "/api/categories" ? CATS : { invoice_id: 9 };
        return Promise.resolve(new Response(JSON.stringify(body)));
      }),
    );
    const onCategory = vi.fn();
    const t = {
      transaction_id: 7,
      amount: "-89.69",
      category_id: null,
      statement_file_id: 5,
    } as unknown as Txn;
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <LineKnown t={t} onCategory={onCategory} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/kept for Juliana’s school/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the statement" })).toHaveAttribute(
      "href",
      "/api/statements/5/file",
    );
    fireEvent.click(await screen.findByRole("button", { name: "Use this category" }));
    expect(onCategory).toHaveBeenCalledWith(42);
    fireEvent.click(screen.getByRole("button", { name: "This is the one" }));
    await waitFor(() =>
      expect(calls.some(([u, i]) => u === "/api/transactions/7/invoice" && i?.method === "PUT")).toBe(true),
    );
  });
});
